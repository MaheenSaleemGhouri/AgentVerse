"""Real Postgres tests for resource-scoped permissions (Increment 6) —
grant/revoke/list via the real routes, plus the composition acceptance
criterion: `require_resource_permission` layered *alongside*
`require_viewer` on a route, passable by a below-admin role holding the
grant.

The composition test mounts a tiny ad-hoc route (not part of the public
API) rather than adding permanent test-only surface to `main.py` — there
is no real `billing` route yet to compose onto, and this is pure
dependency-composition logic that needs no real infrastructure to
verify (unlike the existing `/internal/job-test`-style routes, which
exist because they exercise real Redis/queue wiring a fake can't).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

import pytest
from fastapi import APIRouter, Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.infrastructure.models import AuditLog, User
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
    get_current_identity_optional,
)
from agentverse_api.auth_service.interface.dependencies.require_resource_permission import (
    require_resource_permission,
)
from agentverse_api.auth_service.interface.dependencies.require_role import require_viewer
from agentverse_api.infrastructure.db import get_db_session
from agentverse_api.main import create_app

pytestmark = pytest.mark.integration

_test_router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}")


@_test_router.get("/_test-billing-action")
async def _test_billing_action(
    context: WorkspaceContext = Depends(require_viewer),
    _billing_grant: None = Depends(require_resource_permission("billing", "manage")),
) -> dict[str, str]:
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
        # `get_current_workspace` resolves the session through the
        # optional variant (an API key returns `None` there), so both
        # must be stubbed for a session-authenticated test client.
        app.dependency_overrides[get_current_identity_optional] = lambda: user_id
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        return client

    yield factory

    for client in clients:
        await client.aclose()


async def test_member_with_a_grant_passes_a_route_requiring_both_role_and_grant(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"rp-owner-{unique_name}"
    member = f"rp-member-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, member)

    owner_client = make_client(owner)
    member_client = make_client(member)

    create = await owner_client.post("/api/v1/workspaces", json={"name": f"rp-ws-{unique_name}"})
    workspace_id = create.json()["id"]
    await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"user_id": member, "role": "member"},
    )

    # Below-admin role, no grant yet — passes `require_viewer` (they are
    # a member) but fails the resource-permission check.
    denied = await member_client.get(f"/api/v1/workspaces/{workspace_id}/_test-billing-action")
    assert denied.status_code == 403

    grant = await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/resource-permissions",
        json={"resource_type": "billing", "permission": "manage", "principal_id": member},
    )
    assert grant.status_code == 201

    # Same below-admin role, now holding the grant — passes.
    allowed = await member_client.get(f"/api/v1/workspaces/{workspace_id}/_test-billing-action")
    assert allowed.status_code == 200
    assert allowed.json() == {"workspace_id": workspace_id}

    # The denial was audited, mirroring `require_role`'s own contract.
    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.workspace_id == workspace_id,
            AuditLog.action == "resource_permission.denied",
            AuditLog.actor_user_id == member,
        )
    )
    assert len(result.scalars().all()) == 1


async def test_granting_is_admin_gated_and_non_admin_cannot_grant(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"rp-owner2-{unique_name}"
    member = f"rp-member2-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, member)

    owner_client = make_client(owner)
    member_client = make_client(member)

    create = await owner_client.post("/api/v1/workspaces", json={"name": f"rp-ws2-{unique_name}"})
    workspace_id = create.json()["id"]
    await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"user_id": member, "role": "member"},
    )

    denied = await member_client.post(
        f"/api/v1/workspaces/{workspace_id}/resource-permissions",
        json={"resource_type": "billing", "permission": "manage", "principal_id": member},
    )
    assert denied.status_code == 403


async def test_granting_the_same_tuple_twice_is_idempotent_not_duplicated(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"rp-owner3-{unique_name}"
    member = f"rp-member3-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, member)

    owner_client = make_client(owner)

    create = await owner_client.post("/api/v1/workspaces", json={"name": f"rp-ws3-{unique_name}"})
    workspace_id = create.json()["id"]
    body = {"resource_type": "billing", "permission": "manage", "principal_id": member}

    first = await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/resource-permissions", json=body
    )
    second = await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/resource-permissions", json=body
    )
    assert first.json()["id"] == second.json()["id"]

    listed = await owner_client.get(f"/api/v1/workspaces/{workspace_id}/resource-permissions")
    assert len(listed.json()) == 1


async def test_revoke_removes_the_grant_and_is_workspace_scoped(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"rp-owner4-{unique_name}"
    member = f"rp-member4-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, member)

    owner_client = make_client(owner)

    create_a = await owner_client.post(
        "/api/v1/workspaces", json={"name": f"rp-ws4a-{unique_name}"}
    )
    workspace_a = create_a.json()["id"]
    create_b = await owner_client.post(
        "/api/v1/workspaces", json={"name": f"rp-ws4b-{unique_name}"}
    )
    workspace_b = create_b.json()["id"]

    grant = await owner_client.post(
        f"/api/v1/workspaces/{workspace_a}/resource-permissions",
        json={"resource_type": "billing", "permission": "manage", "principal_id": member},
    )
    permission_id = grant.json()["id"]

    # Revoking via the *other* workspace's URL must not remove it — a
    # cross-workspace id shouldn't reach a row it doesn't own.
    cross_workspace = await owner_client.delete(
        f"/api/v1/workspaces/{workspace_b}/resource-permissions/{permission_id}"
    )
    assert cross_workspace.status_code == 204
    still_listed = await owner_client.get(
        f"/api/v1/workspaces/{workspace_a}/resource-permissions"
    )
    assert len(still_listed.json()) == 1

    revoke = await owner_client.delete(
        f"/api/v1/workspaces/{workspace_a}/resource-permissions/{permission_id}"
    )
    assert revoke.status_code == 204
    now_empty = await owner_client.get(f"/api/v1/workspaces/{workspace_a}/resource-permissions")
    assert now_empty.json() == []
