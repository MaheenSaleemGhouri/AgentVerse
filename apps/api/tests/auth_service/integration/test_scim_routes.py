"""SCIM 2.0 end-to-end through the real app and real Postgres.

The properties worth pinning here are the ones a fake would hide: the
token really resolves the tenant, a token cannot see another
organization's people, provisioning is idempotent under the retries
every SCIM client performs, and deprovisioning removes the membership
without destroying the account.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.infrastructure.models import User
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
    get_current_identity_optional,
)
from agentverse_api.infrastructure.db import get_db_session
from agentverse_api.main import create_app

pytestmark = pytest.mark.integration


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
async def clients(
    db_session: AsyncSession,
) -> AsyncIterator[tuple[Callable[[str], AsyncClient], Callable[[], AsyncClient]]]:
    opened: list[AsyncClient] = []

    async def db_session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    def as_user(user_id: str) -> AsyncClient:
        app = create_app()
        app.dependency_overrides[get_db_session] = db_session_override
        app.dependency_overrides[get_current_identity] = lambda: user_id
        app.dependency_overrides[get_current_identity_optional] = lambda: user_id
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        opened.append(client)
        return client

    def as_idp() -> AsyncClient:
        """No identity override at all — authenticates purely by the
        SCIM token in its `Authorization` header.
        """
        app = create_app()
        app.dependency_overrides[get_db_session] = db_session_override
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        opened.append(client)
        return client

    yield as_user, as_idp

    for client in opened:
        await client.aclose()


async def _org_with_scim_token(admin_client: AsyncClient, *, name: str) -> tuple[str, str]:
    created = await admin_client.post("/api/v1/organizations", json={"name": name})
    assert created.status_code == 201, created.text
    organization_id = created.json()["id"]
    issued = await admin_client.post(
        f"/api/v1/organizations/{organization_id}/scim-tokens",
        json={"name": f"{name}-idp"},
    )
    assert issued.status_code == 201, issued.text
    return organization_id, issued.json()["token"]


async def test_provisioning_creates_an_account_and_a_membership(
    db_session: AsyncSession,
    clients: tuple[Callable[[str], AsyncClient], Callable[[], AsyncClient]],
    unique_name: str,
) -> None:
    as_user, as_idp = clients
    admin = f"scim-admin-{unique_name}"
    await _make_user(db_session, admin)
    organization_id, token = await _org_with_scim_token(
        as_user(admin), name=f"scim-org-{unique_name}"
    )

    email = f"provisioned-{unique_name}@example.com"
    created = await as_idp().post(
        "/scim/v2/Users",
        json={
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": email,
            "name": {"givenName": "Ada", "familyName": "Lovelace"},
            "emails": [{"value": email, "primary": True}],
            "active": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["userName"] == email
    assert body["displayName"] == "Ada Lovelace"
    assert body["active"] is True
    assert created.headers["content-type"].startswith("application/scim+json")

    member = await db_session.execute(
        text(
            "SELECT count(*) FROM organization_members om JOIN users u ON u.id = om.user_id "
            "WHERE om.organization_id = :org AND u.email = :email"
        ),
        {"org": organization_id, "email": email},
    )
    assert member.scalar_one() == 1


async def test_reprovisioning_the_same_person_is_idempotent(
    db_session: AsyncSession,
    clients: tuple[Callable[[str], AsyncClient], Callable[[], AsyncClient]],
    unique_name: str,
) -> None:
    """SCIM clients retry. A duplicate POST must not create a second
    account or a second membership.
    """
    as_user, as_idp = clients
    admin = f"idem-admin-{unique_name}"
    await _make_user(db_session, admin)
    organization_id, token = await _org_with_scim_token(
        as_user(admin), name=f"idem-org-{unique_name}"
    )

    idp = as_idp()
    auth = {"Authorization": f"Bearer {token}"}
    email = f"retry-{unique_name}@example.com"
    payload = {"userName": email, "emails": [{"value": email, "primary": True}]}

    first = await idp.post("/scim/v2/Users", json=payload, headers=auth)
    second = await idp.post("/scim/v2/Users", json=payload, headers=auth)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    count = await db_session.execute(
        text("SELECT count(*) FROM organization_members WHERE organization_id = :org"),
        {"org": organization_id},
    )
    # The admin who created the org, plus exactly one provisioned person.
    assert count.scalar_one() == 2


async def test_deactivate_then_reactivate_through_patch(
    db_session: AsyncSession,
    clients: tuple[Callable[[str], AsyncClient], Callable[[], AsyncClient]],
    unique_name: str,
) -> None:
    as_user, as_idp = clients
    admin = f"patch-admin-{unique_name}"
    await _make_user(db_session, admin)
    _, token = await _org_with_scim_token(as_user(admin), name=f"patch-org-{unique_name}")

    idp = as_idp()
    auth = {"Authorization": f"Bearer {token}"}
    email = f"patched-{unique_name}@example.com"
    created = await idp.post(
        "/scim/v2/Users",
        json={"userName": email, "emails": [{"value": email, "primary": True}]},
        headers=auth,
    )
    user_id = created.json()["id"]

    off = await idp.patch(
        f"/scim/v2/Users/{user_id}",
        json={"Operations": [{"op": "replace", "path": "active", "value": False}]},
        headers=auth,
    )
    assert off.status_code == 200
    assert off.json()["active"] is False

    on = await idp.patch(
        f"/scim/v2/Users/{user_id}",
        json={"Operations": [{"op": "replace", "value": {"active": True}}]},
        headers=auth,
    )
    assert on.json()["active"] is True


async def test_deprovisioning_removes_membership_but_keeps_the_account(
    db_session: AsyncSession,
    clients: tuple[Callable[[str], AsyncClient], Callable[[], AsyncClient]],
    unique_name: str,
) -> None:
    as_user, as_idp = clients
    admin = f"del-admin-{unique_name}"
    await _make_user(db_session, admin)
    organization_id, token = await _org_with_scim_token(
        as_user(admin), name=f"del-org-{unique_name}"
    )

    idp = as_idp()
    auth = {"Authorization": f"Bearer {token}"}
    email = f"deprovisioned-{unique_name}@example.com"
    created = await idp.post(
        "/scim/v2/Users",
        json={"userName": email, "emails": [{"value": email, "primary": True}]},
        headers=auth,
    )
    user_id = created.json()["id"]

    deleted = await idp.delete(f"/scim/v2/Users/{user_id}", headers=auth)
    assert deleted.status_code == 204

    memberships = await db_session.execute(
        text(
            "SELECT count(*) FROM organization_members "
            "WHERE organization_id = :org AND user_id = :user"
        ),
        {"org": organization_id, "user": user_id},
    )
    assert memberships.scalar_one() == 0

    # The account survives: it may belong to other organizations, and
    # runs and audit entries reference it.
    account = await db_session.execute(
        text("SELECT count(*) FROM users WHERE id = :user"), {"user": user_id}
    )
    assert account.scalar_one() == 1


async def test_a_token_cannot_see_another_organizations_people(
    db_session: AsyncSession,
    clients: tuple[Callable[[str], AsyncClient], Callable[[], AsyncClient]],
    unique_name: str,
) -> None:
    as_user, as_idp = clients
    admin = f"iso-admin-{unique_name}"
    await _make_user(db_session, admin)
    admin_client = as_user(admin)

    _, mine_token = await _org_with_scim_token(admin_client, name=f"iso-mine-{unique_name}")
    _, theirs_token = await _org_with_scim_token(admin_client, name=f"iso-theirs-{unique_name}")

    idp = as_idp()
    email = f"theirs-{unique_name}@example.com"
    created = await idp.post(
        "/scim/v2/Users",
        json={"userName": email, "emails": [{"value": email, "primary": True}]},
        headers={"Authorization": f"Bearer {theirs_token}"},
    )
    foreign_user_id = created.json()["id"]

    # Same human administers both organizations, but a token is scoped to
    # exactly one — the other's people must be invisible, not merely
    # forbidden.
    probe = await idp.get(
        f"/scim/v2/Users/{foreign_user_id}",
        headers={"Authorization": f"Bearer {mine_token}"},
    )
    assert probe.status_code == 404

    listed = await idp.get(
        f'/scim/v2/Users?filter=userName eq "{email}"',
        headers={"Authorization": f"Bearer {mine_token}"},
    )
    assert listed.json()["totalResults"] == 0


async def test_a_revoked_token_stops_working(
    db_session: AsyncSession,
    clients: tuple[Callable[[str], AsyncClient], Callable[[], AsyncClient]],
    unique_name: str,
) -> None:
    as_user, as_idp = clients
    admin = f"rev-admin-{unique_name}"
    await _make_user(db_session, admin)
    admin_client = as_user(admin)
    organization_id, token = await _org_with_scim_token(admin_client, name=f"rev-org-{unique_name}")

    idp = as_idp()
    auth = {"Authorization": f"Bearer {token}"}
    assert (await idp.get("/scim/v2/Users", headers=auth)).status_code == 200

    listed = await admin_client.get(f"/api/v1/organizations/{organization_id}/scim-tokens")
    token_id = listed.json()[0]["id"]
    revoked = await admin_client.delete(
        f"/api/v1/organizations/{organization_id}/scim-tokens/{token_id}"
    )
    assert revoked.status_code == 204

    assert (await idp.get("/scim/v2/Users", headers=auth)).status_code == 401


async def test_an_unsupported_filter_returns_a_scim_error_not_everything(
    db_session: AsyncSession,
    clients: tuple[Callable[[str], AsyncClient], Callable[[], AsyncClient]],
    unique_name: str,
) -> None:
    as_user, as_idp = clients
    admin = f"filt-admin-{unique_name}"
    await _make_user(db_session, admin)
    _, token = await _org_with_scim_token(as_user(admin), name=f"filt-org-{unique_name}")

    response = await as_idp().get(
        '/scim/v2/Users?filter=emails.value eq "x@example.com"',
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"]
    assert body["scimType"] == "invalidFilter"


async def test_group_writes_are_refused_explicitly(
    db_session: AsyncSession,
    clients: tuple[Callable[[str], AsyncClient], Callable[[], AsyncClient]],
    unique_name: str,
) -> None:
    """Push-groups must fail loudly: organization membership grants no
    workspace access (ADR-0011), so silently accepting a group write
    would leave an admin believing access had been provisioned.
    """
    as_user, as_idp = clients
    admin = f"grp-admin-{unique_name}"
    await _make_user(db_session, admin)
    _, token = await _org_with_scim_token(as_user(admin), name=f"grp-org-{unique_name}")

    response = await as_idp().post(
        "/scim/v2/Groups",
        json={"displayName": "Engineering"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 501
    assert "read-only" in response.json()["detail"]


async def test_scim_requires_a_token_at_all(
    clients: tuple[Callable[[str], AsyncClient], Callable[[], AsyncClient]],
) -> None:
    _, as_idp = clients
    idp = as_idp()
    assert (await idp.get("/scim/v2/Users")).status_code == 401
    assert (
        await idp.get("/scim/v2/Users", headers={"Authorization": "Bearer av_scim_nope"})
    ).status_code == 401
