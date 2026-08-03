"""Real Postgres tests for tenant-defined roles.

The behaviour that actually matters here is the composition claim: a
custom role can grant a capability from *above* its base tier without
changing what `require_role` answers. If that stopped holding, either
custom roles would be useless or they would silently escalate people
past role floors the rest of the platform still depends on.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

import pytest
from fastapi import APIRouter, Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.domain.permission import Permission
from agentverse_api.auth_service.infrastructure.models import AuditLog, User, WorkspaceMember
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
    get_current_identity_optional,
)
from agentverse_api.auth_service.interface.dependencies.require_permission import (
    require_permission,
)
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_admin,
    require_viewer,
)
from agentverse_api.infrastructure.db import get_db_session
from agentverse_api.main import create_app

pytestmark = pytest.mark.integration

_test_router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}")

#: Built once at import, matching how `require_role` exposes its own
#: pre-built floors — the factory should not run per request.
_require_audit_export = require_permission(Permission.AUDIT_LOG_EXPORT)


@_test_router.get("/_test-audit-export")
async def _test_audit_export(
    context: WorkspaceContext = Depends(require_viewer),
    _grant: WorkspaceContext = Depends(_require_audit_export),
) -> dict[str, str]:
    """Composed exactly as a real route would be: a role floor *and* a
    permission, neither replacing the other.
    """
    return {"workspace_id": context.workspace_id}


@_test_router.get("/_test-admin-floor")
async def _test_admin_floor(
    context: WorkspaceContext = Depends(require_admin),
) -> dict[str, str]:
    """Role floor only — must stay closed to a custom role whose base
    tier is below admin, no matter what permissions it was granted.
    """
    return {"workspace_id": context.workspace_id}


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

    async def db_session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    def factory(user_id: str) -> AsyncClient:
        app = create_app()
        app.include_router(_test_router)
        app.dependency_overrides[get_db_session] = db_session_override
        app.dependency_overrides[get_current_identity] = lambda: user_id
        app.dependency_overrides[get_current_identity_optional] = lambda: user_id
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        return client

    yield factory

    for client in clients:
        await client.aclose()


async def test_custom_role_grants_above_its_tier_without_changing_its_rank(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"cr-owner-{unique_name}"
    member = f"cr-member-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, member)

    owner_client = make_client(owner)
    member_client = make_client(member)

    create = await owner_client.post("/api/v1/workspaces", json={"name": f"cr-ws-{unique_name}"})
    workspace_id = create.json()["id"]
    await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"user_id": member, "role": "member"},
    )

    # A plain member does not hold audit_log:export (that starts at analyst).
    denied = await member_client.get(f"/api/v1/workspaces/{workspace_id}/_test-audit-export")
    assert denied.status_code == 403

    role = await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/roles",
        json={
            "name": "Support Engineer",
            "base_role": "member",
            "permissions": [Permission.AUDIT_LOG_EXPORT.value],
        },
    )
    assert role.status_code == 201
    role_id = role.json()["id"]

    # Assigning the custom role deliberately leaves `role` alone — only
    # `custom_role_id` changes, which is what keeps the rank stable.
    await db_session.execute(
        update(WorkspaceMember)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == member,
        )
        .values(custom_role_id=role_id)
    )
    await db_session.commit()

    # The granted capability now passes...
    allowed = await member_client.get(f"/api/v1/workspaces/{workspace_id}/_test-audit-export")
    assert allowed.status_code == 200

    # ...while the admin floor stays shut. This is the whole invariant.
    still_denied = await member_client.get(f"/api/v1/workspaces/{workspace_id}/_test-admin-floor")
    assert still_denied.status_code == 403

    # The earlier denial was audited, mirroring `require_role`'s contract.
    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.workspace_id == workspace_id,
            AuditLog.action == "permission.denied",
            AuditLog.actor_user_id == member,
        )
    )
    assert len(result.scalars().all()) >= 1


async def test_creating_a_role_is_admin_gated_and_rejects_unknown_permissions(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"cr-owner2-{unique_name}"
    member = f"cr-member2-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, member)

    owner_client = make_client(owner)
    member_client = make_client(member)

    create = await owner_client.post("/api/v1/workspaces", json={"name": f"cr-ws2-{unique_name}"})
    workspace_id = create.json()["id"]
    await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"user_id": member, "role": "member"},
    )

    forbidden = await member_client.post(
        f"/api/v1/workspaces/{workspace_id}/roles",
        json={"name": "Sneaky", "base_role": "owner", "permissions": []},
    )
    assert forbidden.status_code == 403

    # A mistyped permission is refused outright rather than silently
    # dropped, so an admin is never left believing a grant took effect.
    bad = await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/roles",
        json={
            "name": "Typo Role",
            "base_role": "member",
            "permissions": ["audit_log:exprot"],
        },
    )
    assert bad.status_code == 422


async def test_custom_roles_are_workspace_scoped_and_cross_tenant_reads_404(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner_a = f"cr-a-{unique_name}"
    owner_b = f"cr-b-{unique_name}"
    await _make_user(db_session, owner_a)
    await _make_user(db_session, owner_b)

    client_a = make_client(owner_a)
    client_b = make_client(owner_b)

    ws_a = (
        await client_a.post("/api/v1/workspaces", json={"name": f"cr-wsa-{unique_name}"})
    ).json()["id"]
    ws_b = (
        await client_b.post("/api/v1/workspaces", json={"name": f"cr-wsb-{unique_name}"})
    ).json()["id"]

    role = await client_a.post(
        f"/api/v1/workspaces/{ws_a}/roles",
        json={"name": "A Only", "base_role": "member", "permissions": []},
    )
    role_id = role.json()["id"]

    # B owns their own workspace, so this is a permission-passing request
    # that must still fail — the role belongs to another tenant, and the
    # answer must not reveal that the id is real (Rule 11).
    cross = await client_b.get(f"/api/v1/workspaces/{ws_b}/roles/{role_id}")
    assert cross.status_code == 404

    # And B's own listing never contains A's role.
    listing = await client_b.get(f"/api/v1/workspaces/{ws_b}/roles")
    assert listing.status_code == 200
    assert listing.json() == []


async def test_builtin_matrix_is_served_to_any_member(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"cr-owner3-{unique_name}"
    await _make_user(db_session, owner)
    client = make_client(owner)

    workspace_id = (
        await client.post("/api/v1/workspaces", json={"name": f"cr-ws3-{unique_name}"})
    ).json()["id"]

    response = await client.get(f"/api/v1/workspaces/{workspace_id}/roles/builtin")
    assert response.status_code == 200
    body = response.json()

    assert [entry["role"] for entry in body] == [
        "owner",
        "admin",
        "manager",
        "developer",
        "analyst",
        "member",
        "viewer",
    ]
    # Served from the server's own matrix so the UI can never drift from
    # enforcement — owner holds everything, viewer holds only reads.
    owner_perms = next(e for e in body if e["role"] == "owner")["permissions"]
    viewer_perms = next(e for e in body if e["role"] == "viewer")["permissions"]
    assert set(owner_perms) == {p.value for p in Permission}
    assert all(p.endswith(":view") for p in viewer_perms)
