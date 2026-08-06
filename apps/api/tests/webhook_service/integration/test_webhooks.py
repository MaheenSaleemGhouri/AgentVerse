"""Webhook endpoints and dispatch, against real Postgres.

Three things worth proving here rather than against a fake:

- a customer-supplied URL pointing into private space is refused at
  write time, by the same guard agent tool calls use;
- the signing secret round-trips through the envelope vault, and
  ciphertext moved to another row does not decrypt;
- dispatch is idempotent because of a unique index, not a check two
  concurrent dispatches would both pass.
"""

from __future__ import annotations

import uuid

import pytest
from agentverse_shared.security.envelope import CredentialVault, KeyRing
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.webhook_service.application.webhook_service import (
    EndpointNotFoundError,
    UnsafeWebhookUrlError,
    WebhookService,
    generate_secret,
    serialize_body,
)
from agentverse_api.webhook_service.domain.endpoint import (
    InvalidEventTypeError,
    WebhookEvent,
)
from agentverse_api.webhook_service.domain.signing import sign, verify
from agentverse_api.webhook_service.infrastructure.repositories import (
    SqlDeliveryRepository,
    SqlEndpointRepository,
)

pytestmark = pytest.mark.integration

_URL = "https://example.com/hooks/agentverse"


def _vault() -> CredentialVault:
    return CredentialVault(KeyRing.from_env())


def _service(session: AsyncSession) -> WebhookService:
    return WebhookService(
        endpoints=SqlEndpointRepository(session, _vault()),
        deliveries=SqlDeliveryRepository(session),
    )


async def _workspace(session: AsyncSession) -> str:
    workspace_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO workspaces (id, name, slug, created_at) "
            "VALUES (:id, 'Webhook Test', :slug, now())"
        ),
        {"id": workspace_id, "slug": f"ws-{workspace_id[:8]}"},
    )
    await session.flush()
    return workspace_id


class TestUrlSafety:
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/hook",
            "http://10.0.0.5/hook",
            "http://192.168.1.1/hook",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/hook",
        ],
    )
    async def test_a_private_destination_is_refused_at_write_time(
        self, db_session: AsyncSession, url: str
    ) -> None:
        # A customer-supplied URL is an SSRF primitive: without this the
        # platform is a proxy into its own network, and the metadata
        # address is a credential exfiltration path.
        workspace = await _workspace(db_session)
        with pytest.raises(UnsafeWebhookUrlError):
            await _service(db_session).create_endpoint(
                workspace_id=workspace,
                url=url,
                description="",
                events=["run.completed"],
            )
        await db_session.rollback()

    async def test_a_non_http_scheme_is_refused(self, db_session: AsyncSession) -> None:
        workspace = await _workspace(db_session)
        with pytest.raises(UnsafeWebhookUrlError):
            await _service(db_session).create_endpoint(
                workspace_id=workspace,
                url="file:///etc/passwd",
                description="",
                events=["run.completed"],
            )
        await db_session.rollback()

    async def test_the_refusal_names_the_reason(self, db_session: AsyncSession) -> None:
        # A customer told "invalid URL" when they typed a private address
        # will retype the same address.
        workspace = await _workspace(db_session)
        with pytest.raises(UnsafeWebhookUrlError) as exc:
            await _service(db_session).create_endpoint(
                workspace_id=workspace,
                url="http://10.0.0.5/hook",
                description="",
                events=["run.completed"],
            )
        assert exc.value.reason
        await db_session.rollback()

    async def test_the_database_also_refuses_a_non_http_url(self, db_session: AsyncSession) -> None:
        # A row inserted by a fixture or a migration bypasses Pydantic
        # and the service, and a relative URL would then fail at delivery
        # time rather than at write time.
        workspace = await _workspace(db_session)
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO webhook_endpoints "
                    "(id, workspace_id, url, secret_ciphertext, wrapped_dek, key_version) "
                    "VALUES (gen_random_uuid(), :ws, '/relative', '\\x00', '\\x00', 'v1')"
                ),
                {"ws": workspace},
            )
        await db_session.rollback()


class TestEndpointLifecycle:
    async def test_creating_returns_the_secret_once(self, db_session: AsyncSession) -> None:
        workspace = await _workspace(db_session)
        created = await _service(db_session).create_endpoint(
            workspace_id=workspace,
            url=_URL,
            description="Ops alerts",
            events=["run.completed", "run.failed"],
        )
        assert created.secret.startswith("whsec_")
        assert created.endpoint.events == frozenset(
            {WebhookEvent.RUN_COMPLETED, WebhookEvent.RUN_FAILED}
        )
        await db_session.rollback()

    async def test_the_secret_is_never_returned_by_a_later_read(
        self, db_session: AsyncSession
    ) -> None:
        # Stored decryptably because the customer's verifier needs it —
        # which is a different question from whether the API hands it
        # back on demand.
        workspace = await _workspace(db_session)
        service = _service(db_session)
        await service.create_endpoint(
            workspace_id=workspace, url=_URL, description="", events=["run.completed"]
        )
        listed = await service.list_endpoints(workspace_id=workspace)
        assert not hasattr(listed[0], "secret")
        await db_session.rollback()

    async def test_the_stored_secret_round_trips_through_the_vault(
        self, db_session: AsyncSession
    ) -> None:
        workspace = await _workspace(db_session)
        created = await _service(db_session).create_endpoint(
            workspace_id=workspace, url=_URL, description="", events=["run.completed"]
        )
        row = await db_session.execute(
            text(
                "SELECT secret_ciphertext, wrapped_dek, key_version "
                "FROM webhook_endpoints WHERE id = :id"
            ),
            {"id": created.endpoint.id},
        )
        ciphertext, wrapped, version = row.one()
        from agentverse_shared.security.envelope import SealedSecret

        opened = _vault().open(
            SealedSecret(
                ciphertext=bytes(ciphertext), wrapped_dek=bytes(wrapped), key_version=version
            ),
            associated_data=f"webhook:{workspace}:{created.endpoint.id}".encode(),
        )
        assert opened == created.secret
        await db_session.rollback()

    async def test_ciphertext_moved_to_another_row_does_not_decrypt(
        self, db_session: AsyncSession
    ) -> None:
        # The associated data binds the sealed secret to its row, so
        # ciphertext copied elsewhere fails rather than silently becoming
        # that endpoint's secret.
        workspace = await _workspace(db_session)
        created = await _service(db_session).create_endpoint(
            workspace_id=workspace, url=_URL, description="", events=["run.completed"]
        )
        row = await db_session.execute(
            text(
                "SELECT secret_ciphertext, wrapped_dek, key_version "
                "FROM webhook_endpoints WHERE id = :id"
            ),
            {"id": created.endpoint.id},
        )
        ciphertext, wrapped, version = row.one()
        from agentverse_shared.security.envelope import SealedSecret

        with pytest.raises(Exception):  # noqa: B017 - any decryption failure is the point
            _vault().open(
                SealedSecret(
                    ciphertext=bytes(ciphertext), wrapped_dek=bytes(wrapped), key_version=version
                ),
                associated_data=f"webhook:{workspace}:{uuid.uuid4()}".encode(),
            )
        await db_session.rollback()

    async def test_rotating_produces_a_different_secret(self, db_session: AsyncSession) -> None:
        workspace = await _workspace(db_session)
        service = _service(db_session)
        created = await service.create_endpoint(
            workspace_id=workspace, url=_URL, description="", events=["run.completed"]
        )
        rotated = await service.rotate_secret(
            workspace_id=workspace, endpoint_id=created.endpoint.id
        )
        assert rotated != created.secret
        await db_session.rollback()

    async def test_re_enabling_clears_the_failure_counter(self, db_session: AsyncSession) -> None:
        # Without this an endpoint disabled by 20 failures would be
        # switched back on and disabled again by its 21st, which reads as
        # the toggle being broken.
        workspace = await _workspace(db_session)
        service = _service(db_session)
        created = await service.create_endpoint(
            workspace_id=workspace, url=_URL, description="", events=["run.completed"]
        )
        await db_session.execute(
            text(
                "UPDATE webhook_endpoints SET consecutive_failures = 20, is_active = false, "
                "disabled_reason = 'test' WHERE id = :id"
            ),
            {"id": created.endpoint.id},
        )
        updated = await service.update_endpoint(
            workspace_id=workspace, endpoint_id=created.endpoint.id, is_active=True
        )
        assert updated.consecutive_failures == 0
        assert updated.disabled_reason is None
        await db_session.rollback()

    async def test_an_unknown_event_is_refused(self, db_session: AsyncSession) -> None:
        workspace = await _workspace(db_session)
        with pytest.raises(InvalidEventTypeError):
            await _service(db_session).create_endpoint(
                workspace_id=workspace, url=_URL, description="", events=["run.complete"]
            )
        await db_session.rollback()


class TestTenantIsolation:
    async def test_another_workspaces_endpoint_is_not_found(self, db_session: AsyncSession) -> None:
        # The repository queries are workspace-scoped, so a cross-tenant
        # id is indistinguishable from a missing one — which is the point
        # (Rule 11).
        owner = await _workspace(db_session)
        stranger = await _workspace(db_session)
        service = _service(db_session)
        created = await service.create_endpoint(
            workspace_id=owner, url=_URL, description="", events=["run.completed"]
        )
        with pytest.raises(EndpointNotFoundError):
            await service.rotate_secret(workspace_id=stranger, endpoint_id=created.endpoint.id)
        await db_session.rollback()

    async def test_listing_only_returns_this_workspaces_endpoints(
        self, db_session: AsyncSession
    ) -> None:
        owner = await _workspace(db_session)
        stranger = await _workspace(db_session)
        service = _service(db_session)
        await service.create_endpoint(
            workspace_id=owner, url=_URL, description="", events=["run.completed"]
        )
        assert await service.list_endpoints(workspace_id=stranger) == []
        assert len(await service.list_endpoints(workspace_id=owner)) == 1
        await db_session.rollback()


class TestDispatch:
    async def test_only_subscribed_endpoints_are_queued(self, db_session: AsyncSession) -> None:
        workspace = await _workspace(db_session)
        service = _service(db_session)
        await service.create_endpoint(
            workspace_id=workspace, url=_URL, description="", events=["run.completed"]
        )
        await service.create_endpoint(
            workspace_id=workspace,
            url="https://example.com/other",
            description="",
            events=["billing.quota_exceeded"],
        )

        queued = await service.dispatch(
            workspace_id=workspace,
            event=WebhookEvent.RUN_COMPLETED,
            event_id=str(uuid.uuid4()),
            payload={"run_id": "r1"},
        )
        assert queued == 1
        await db_session.rollback()

    async def test_a_disabled_endpoint_receives_nothing(self, db_session: AsyncSession) -> None:
        workspace = await _workspace(db_session)
        service = _service(db_session)
        created = await service.create_endpoint(
            workspace_id=workspace, url=_URL, description="", events=["run.completed"]
        )
        await service.update_endpoint(
            workspace_id=workspace, endpoint_id=created.endpoint.id, is_active=False
        )
        queued = await service.dispatch(
            workspace_id=workspace,
            event=WebhookEvent.RUN_COMPLETED,
            event_id=str(uuid.uuid4()),
            payload={},
        )
        assert queued == 0
        await db_session.rollback()

    async def test_dispatching_the_same_event_twice_queues_once(
        self, db_session: AsyncSession
    ) -> None:
        # The property that makes a redelivered job safe: `event_id` is
        # derived from the row that caused the event, so the second
        # dispatch is absorbed by the unique index rather than sending
        # the customer a duplicate (Rule 14).
        workspace = await _workspace(db_session)
        service = _service(db_session)
        await service.create_endpoint(
            workspace_id=workspace, url=_URL, description="", events=["run.completed"]
        )
        event_id = str(uuid.uuid4())

        first = await service.dispatch(
            workspace_id=workspace,
            event=WebhookEvent.RUN_COMPLETED,
            event_id=event_id,
            payload={"run_id": "r1"},
        )
        second = await service.dispatch(
            workspace_id=workspace,
            event=WebhookEvent.RUN_COMPLETED,
            event_id=event_id,
            payload={"run_id": "r1"},
        )
        assert (first, second) == (1, 0)
        await db_session.rollback()

    async def test_idempotency_is_enforced_by_the_database(self, db_session: AsyncSession) -> None:
        workspace = await _workspace(db_session)
        service = _service(db_session)
        created = await service.create_endpoint(
            workspace_id=workspace, url=_URL, description="", events=["run.completed"]
        )
        insert = text(
            "INSERT INTO webhook_deliveries "
            "(id, workspace_id, endpoint_id, event_type, event_id) "
            "VALUES (gen_random_uuid(), :ws, :ep, 'run.completed', 'evt-1')"
        )
        params = {"ws": workspace, "ep": created.endpoint.id}
        await db_session.execute(insert, params)
        with pytest.raises(IntegrityError):
            await db_session.execute(insert, params)
        await db_session.rollback()

    async def test_the_envelope_carries_a_type_and_a_stable_id(
        self, db_session: AsyncSession
    ) -> None:
        # A receiver routes on `type` and dedupes on `id` without knowing
        # which event it is.
        workspace = await _workspace(db_session)
        service = _service(db_session)
        created = await service.create_endpoint(
            workspace_id=workspace, url=_URL, description="", events=["run.completed"]
        )
        await service.dispatch(
            workspace_id=workspace,
            event=WebhookEvent.RUN_COMPLETED,
            event_id="run-42",
            payload={"run_id": "run-42"},
        )
        row = await db_session.execute(
            text("SELECT payload FROM webhook_deliveries WHERE endpoint_id = :ep"),
            {"ep": created.endpoint.id},
        )
        payload = row.scalar_one()
        assert payload["type"] == "run.completed"
        assert payload["api_version"] == "v1"
        assert payload["data"] == {"run_id": "run-42"}
        assert payload["id"].startswith("evt_")
        await db_session.rollback()

    async def test_deliveries_are_visible_to_their_workspace_only(
        self, db_session: AsyncSession
    ) -> None:
        owner = await _workspace(db_session)
        stranger = await _workspace(db_session)
        service = _service(db_session)
        await service.create_endpoint(
            workspace_id=owner, url=_URL, description="", events=["run.completed"]
        )
        await service.dispatch(
            workspace_id=owner,
            event=WebhookEvent.RUN_COMPLETED,
            event_id=str(uuid.uuid4()),
            payload={},
        )
        assert await service.list_deliveries(workspace_id=stranger) == []
        assert len(await service.list_deliveries(workspace_id=owner)) == 1
        await db_session.rollback()

    async def test_dispatching_to_nobody_is_not_an_error(self, db_session: AsyncSession) -> None:
        # A workspace with no endpoints is the common case, and it must
        # not raise on the completion path of every agent run.
        workspace = await _workspace(db_session)
        queued = await _service(db_session).dispatch(
            workspace_id=workspace,
            event=WebhookEvent.RUN_COMPLETED,
            event_id=str(uuid.uuid4()),
            payload={},
        )
        assert queued == 0
        await db_session.rollback()


class TestBodySerialization:
    def test_the_body_is_byte_stable(self) -> None:
        # The signature covers these bytes. A re-serialization that
        # differs by one space produces a signature that fails at every
        # customer, and the bug is invisible from our side.
        envelope = {"b": 2, "a": 1}
        assert serialize_body(envelope) == serialize_body({"a": 1, "b": 2})
        assert serialize_body(envelope) == '{"a":1,"b":2}'

    def test_a_signature_over_the_serialized_body_verifies(self) -> None:
        secret = generate_secret()
        body = serialize_body({"id": "evt_1", "type": "run.completed"})
        assert verify(
            secret=secret,
            timestamp=1_800_000_000,
            body=body,
            provided=sign(secret=secret, timestamp=1_800_000_000, body=body),
        )
