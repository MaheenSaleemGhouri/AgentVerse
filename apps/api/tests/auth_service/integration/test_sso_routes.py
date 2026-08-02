"""Real-Postgres tests for org SSO configuration (Increment 8).

The security-critical property here is that the client secret is sealed
on write and never present in any read path — asserted against the real
row and the real response, not a fake.
"""

from __future__ import annotations

import base64
import os
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

import pytest
from agentverse_shared.security.envelope import CredentialVault, KeyRing
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.infrastructure.models import SsoConfiguration, User
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
    get_current_identity_optional,
)
from agentverse_api.infrastructure.db import get_db_session
from agentverse_api.main import create_app
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_credential_vault,
)

pytestmark = pytest.mark.integration

_SECRET = "super-secret-client-value"


async def _make_user(session: AsyncSession, user_id: str) -> None:
    session.add(
        User(
            id=user_id,
            name=user_id,
            email=f"{user_id}@example.com",
            email_verified=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    await session.commit()


@pytest.fixture
async def make_client(
    db_session: AsyncSession,
) -> AsyncIterator[Callable[[str], AsyncClient]]:
    clients: list[AsyncClient] = []
    # A real vault with a generated key — the sealing path is precisely
    # what these tests assert, and stubbing it would prove nothing
    # (mirrors `test_integrations_route.py`'s harness).
    vault = CredentialVault(
        KeyRing.from_env(
            {"AGENTVERSE_CREDENTIAL_KEK_V1": base64.b64encode(os.urandom(32)).decode()},
            active_version="v1",
        )
    )

    async def db_session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    def factory(user_id: str) -> AsyncClient:
        app = create_app()
        app.dependency_overrides[get_db_session] = db_session_override
        app.dependency_overrides[get_current_identity] = lambda: user_id
        # `get_current_workspace` resolves the session through the
        # optional variant (an API key returns `None` there), so both
        # must be stubbed for a session-authenticated test client.
        app.dependency_overrides[get_current_identity_optional] = lambda: user_id
        app.dependency_overrides[get_credential_vault] = lambda: vault
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        return client

    yield factory

    for client in clients:
        await client.aclose()


async def test_saving_oidc_config_seals_the_secret_and_never_returns_it(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"sso-owner-{unique_name}"
    await _make_user(db_session, owner)
    client = make_client(owner)

    create = await client.post("/api/v1/organizations", json={"name": f"sso-org-{unique_name}"})
    org_id = create.json()["id"]

    saved = await client.put(
        f"/api/v1/organizations/{org_id}/sso",
        json={
            "protocol": "oidc",
            "preset": "azure_ad",
            "issuer_url": "https://login.microsoftonline.com/tenant/v2.0",
            "client_id": "client-abc",
            "client_secret": _SECRET,
            "protocol_config": {"scopes": "openid email profile"},
            "enabled": True,
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["protocol"] == "oidc"
    assert body["preset"] == "azure_ad"
    assert body["has_client_secret"] is True
    assert body["enabled"] is True
    # The secret is absent from the response by construction.
    assert "client_secret" not in body
    assert _SECRET not in saved.text

    # And is genuinely encrypted at rest, not merely omitted from the API.
    result = await db_session.execute(
        select(SsoConfiguration).where(SsoConfiguration.organization_id == org_id)
    )
    row = result.scalars().one()
    assert row.client_secret_ciphertext is not None
    assert _SECRET.encode() not in row.client_secret_ciphertext
    assert row.wrapped_dek is not None
    assert row.key_version is not None

    listed = await client.get(f"/api/v1/organizations/{org_id}/sso")
    assert _SECRET not in listed.text


async def test_saving_again_without_a_secret_keeps_the_stored_one(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    """Editing the issuer URL must not silently wipe the secret."""
    owner = f"sso-owner2-{unique_name}"
    await _make_user(db_session, owner)
    client = make_client(owner)

    create = await client.post("/api/v1/organizations", json={"name": f"sso-org2-{unique_name}"})
    org_id = create.json()["id"]

    await client.put(
        f"/api/v1/organizations/{org_id}/sso",
        json={
            "protocol": "oidc",
            "issuer_url": "https://idp.example.com",
            "client_id": "client-abc",
            "client_secret": _SECRET,
            "enabled": False,
        },
    )
    before = await db_session.execute(
        select(SsoConfiguration.client_secret_ciphertext).where(
            SsoConfiguration.organization_id == org_id
        )
    )
    original_ciphertext = before.scalars().one()

    updated = await client.put(
        f"/api/v1/organizations/{org_id}/sso",
        json={
            "protocol": "oidc",
            "issuer_url": "https://idp-2.example.com",
            "client_id": "client-abc",
            "enabled": False,
        },
    )
    assert updated.json()["issuer_url"] == "https://idp-2.example.com"
    assert updated.json()["has_client_secret"] is True

    after = await db_session.execute(
        select(SsoConfiguration.client_secret_ciphertext).where(
            SsoConfiguration.organization_id == org_id
        )
    )
    assert after.scalars().one() == original_ciphertext


async def test_saml_uses_the_same_table_with_no_schema_change(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    """8b's acceptance shape: SAML is a `protocol` value plus JSONB
    extras — no new column, no migration."""
    owner = f"sso-owner3-{unique_name}"
    await _make_user(db_session, owner)
    client = make_client(owner)

    create = await client.post("/api/v1/organizations", json={"name": f"sso-org3-{unique_name}"})
    org_id = create.json()["id"]

    saved = await client.put(
        f"/api/v1/organizations/{org_id}/sso",
        json={
            "protocol": "saml",
            "preset": "okta",
            "protocol_config": {
                "idp_metadata_url": "https://okta.example.com/app/x/sso/saml/metadata",
                "idp_entity_id": "http://www.okta.com/exk123",
            },
            "enabled": False,
        },
    )
    assert saved.status_code == 200
    assert saved.json()["protocol"] == "saml"
    assert saved.json()["protocol_config"]["idp_entity_id"] == "http://www.okta.com/exk123"

    # OIDC and SAML coexist for one organization.
    await client.put(
        f"/api/v1/organizations/{org_id}/sso",
        json={"protocol": "oidc", "issuer_url": "https://idp.example.com", "enabled": False},
    )
    listed = await client.get(f"/api/v1/organizations/{org_id}/sso")
    assert {c["protocol"] for c in listed.json()} == {"oidc", "saml"}


async def test_sso_config_is_org_admin_gated_and_cross_org_is_404(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"sso-owner4-{unique_name}"
    member = f"sso-member4-{unique_name}"
    outsider = f"sso-outsider4-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, member)
    await _make_user(db_session, outsider)

    owner_client = make_client(owner)
    member_client = make_client(member)
    outsider_client = make_client(outsider)

    create = await owner_client.post(
        "/api/v1/organizations", json={"name": f"sso-org4-{unique_name}"}
    )
    org_id = create.json()["id"]
    await owner_client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": member, "role": "member"},
    )

    # A member of the org, but below admin.
    denied = await member_client.get(f"/api/v1/organizations/{org_id}/sso")
    assert denied.status_code == 403

    # Not a member at all — existence must not leak (Rule 11).
    hidden = await outsider_client.get(f"/api/v1/organizations/{org_id}/sso")
    assert hidden.status_code == 404


async def test_deleting_a_configuration_removes_it(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"sso-owner5-{unique_name}"
    await _make_user(db_session, owner)
    client = make_client(owner)

    create = await client.post("/api/v1/organizations", json={"name": f"sso-org5-{unique_name}"})
    org_id = create.json()["id"]
    saved = await client.put(
        f"/api/v1/organizations/{org_id}/sso",
        json={"protocol": "oidc", "issuer_url": "https://idp.example.com", "enabled": False},
    )
    config_id = saved.json()["id"]

    removed = await client.delete(f"/api/v1/organizations/{org_id}/sso/{config_id}")
    assert removed.status_code == 204
    assert (await client.get(f"/api/v1/organizations/{org_id}/sso")).json() == []
