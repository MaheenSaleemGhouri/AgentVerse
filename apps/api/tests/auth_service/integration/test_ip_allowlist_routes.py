"""Real-Postgres tests for the IP allowlist (Increment 7.4) — CRUD via
the real admin-gated routes, plus the enforcement composition: a route
depending on `enforce_ip_allowlist` *alongside* `require_viewer`.

Like `test_resource_permissions.py`, the enforcement test mounts a tiny
ad-hoc route rather than adding permanent test-only surface to
`main.py` — no product route composes this dependency yet, and the
logic under test is pure dependency composition.
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
from agentverse_api.auth_service.interface.dependencies.enforce_ip_allowlist import (
    enforce_ip_allowlist,
)
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
    get_current_identity_optional,
)
from agentverse_api.auth_service.interface.dependencies.require_role import require_viewer
from agentverse_api.infrastructure.db import get_db_session
from agentverse_api.main import create_app

pytestmark = pytest.mark.integration

_test_router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}")


@_test_router.get("/_test-ip-guarded")
async def _test_ip_guarded(
    context: WorkspaceContext = Depends(require_viewer),
    _ip_ok: None = Depends(enforce_ip_allowlist),
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


async def test_an_unrestricted_workspace_allows_any_ip(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    """Every pre-existing workspace has zero allowlist rows — this is the
    test that proves they are unaffected by the feature existing."""
    owner = f"ip-owner-{unique_name}"
    await _make_user(db_session, owner)
    client = make_client(owner)

    create = await client.post("/api/v1/workspaces", json={"name": f"ip-ws-{unique_name}"})
    workspace_id = create.json()["id"]

    response = await client.get(
        f"/api/v1/workspaces/{workspace_id}/_test-ip-guarded",
        headers={"X-Forwarded-For": "203.0.113.9"},
    )
    assert response.status_code == 200


async def test_a_restricted_workspace_denies_outside_traffic_and_audits_it(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"ip-owner2-{unique_name}"
    await _make_user(db_session, owner)
    client = make_client(owner)

    create = await client.post("/api/v1/workspaces", json={"name": f"ip-ws2-{unique_name}"})
    workspace_id = create.json()["id"]

    added = await client.post(
        f"/api/v1/workspaces/{workspace_id}/ip-allowlist",
        json={"cidr": "10.0.0.0/8", "label": "Office"},
    )
    assert added.status_code == 201

    inside = await client.get(
        f"/api/v1/workspaces/{workspace_id}/_test-ip-guarded",
        headers={"X-Forwarded-For": "10.1.2.3"},
    )
    assert inside.status_code == 200

    outside = await client.get(
        f"/api/v1/workspaces/{workspace_id}/_test-ip-guarded",
        headers={"X-Forwarded-For": "203.0.113.9"},
    )
    assert outside.status_code == 403

    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.workspace_id == workspace_id,
            AuditLog.action == "ip.denied",
            AuditLog.actor_user_id == owner,
        )
    )
    assert len(result.scalars().all()) == 1


async def test_managing_the_allowlist_stays_reachable_from_a_blocked_ip(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    """The escape hatch: an admin who locks themselves out with a typo
    must still be able to reach the allowlist routes to fix it."""
    owner = f"ip-owner3-{unique_name}"
    await _make_user(db_session, owner)
    client = make_client(owner)

    create = await client.post("/api/v1/workspaces", json={"name": f"ip-ws3-{unique_name}"})
    workspace_id = create.json()["id"]
    added = await client.post(
        f"/api/v1/workspaces/{workspace_id}/ip-allowlist",
        json={"cidr": "10.0.0.0/8", "label": None},
    )
    entry_id = added.json()["id"]

    # From an IP the allowlist now excludes:
    listed = await client.get(
        f"/api/v1/workspaces/{workspace_id}/ip-allowlist",
        headers={"X-Forwarded-For": "203.0.113.9"},
    )
    assert listed.status_code == 200

    removed = await client.delete(
        f"/api/v1/workspaces/{workspace_id}/ip-allowlist/{entry_id}",
        headers={"X-Forwarded-For": "203.0.113.9"},
    )
    assert removed.status_code == 204

    reopened = await client.get(
        f"/api/v1/workspaces/{workspace_id}/_test-ip-guarded",
        headers={"X-Forwarded-For": "203.0.113.9"},
    )
    assert reopened.status_code == 200


async def test_allowlist_management_is_admin_gated_and_rejects_bad_cidr(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"ip-owner4-{unique_name}"
    member = f"ip-member4-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, member)

    owner_client = make_client(owner)
    member_client = make_client(member)

    create = await owner_client.post(
        "/api/v1/workspaces", json={"name": f"ip-ws4-{unique_name}"}
    )
    workspace_id = create.json()["id"]
    await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"user_id": member, "role": "member"},
    )

    denied = await member_client.post(
        f"/api/v1/workspaces/{workspace_id}/ip-allowlist",
        json={"cidr": "10.0.0.0/8", "label": None},
    )
    assert denied.status_code == 403

    bad = await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/ip-allowlist",
        json={"cidr": "not-an-ip", "label": None},
    )
    assert bad.status_code == 422


async def test_one_workspaces_restriction_never_affects_another(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"ip-owner5-{unique_name}"
    await _make_user(db_session, owner)
    client = make_client(owner)

    create_a = await client.post("/api/v1/workspaces", json={"name": f"ip-ws5a-{unique_name}"})
    workspace_a = create_a.json()["id"]
    create_b = await client.post("/api/v1/workspaces", json={"name": f"ip-ws5b-{unique_name}"})
    workspace_b = create_b.json()["id"]

    await client.post(
        f"/api/v1/workspaces/{workspace_a}/ip-allowlist",
        json={"cidr": "10.0.0.0/8", "label": None},
    )

    blocked_in_a = await client.get(
        f"/api/v1/workspaces/{workspace_a}/_test-ip-guarded",
        headers={"X-Forwarded-For": "203.0.113.9"},
    )
    assert blocked_in_a.status_code == 403

    still_open_in_b = await client.get(
        f"/api/v1/workspaces/{workspace_b}/_test-ip-guarded",
        headers={"X-Forwarded-For": "203.0.113.9"},
    )
    assert still_open_in_b.status_code == 200
