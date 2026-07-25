"""Real end-to-end RBAC tests through the actual FastAPI app + real
Postgres — the exact scenario `docs/roadmap.md` Phase 1 names as its
top risk: getting 403-vs-404 wrong on a single-workspace fixture that
never exercises the cross-tenant path. This suite always uses at least
two real workspaces (`decision-log.md` #22).

`get_current_identity` is overridden per test to a fixed user id — this
replaces real Better Auth JWT verification (covered separately by
`tests/auth_service/infrastructure/test_jwt_verifier.py`), not the
Postgres-backed authorization logic this suite actually exercises.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.infrastructure.models import AuditLog, User
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
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
async def make_client(
    db_session: AsyncSession,
) -> AsyncIterator[Callable[[str], AsyncClient]]:
    """Returns a factory: `make_client("alice")` gives an `AsyncClient`
    hitting the real app, authenticated as "alice", sharing the same
    real `db_session` the test itself uses to set up fixture data.
    """
    clients: list[AsyncClient] = []

    async def db_session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    def factory(user_id: str) -> AsyncClient:
        app = create_app()
        app.dependency_overrides[get_db_session] = db_session_override
        app.dependency_overrides[get_current_identity] = lambda: user_id
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        return client

    yield factory

    for client in clients:
        await client.aclose()


async def test_cross_workspace_access_is_404_not_403(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    user_a = f"user-a-{unique_name}"
    user_b = f"user-b-{unique_name}"
    await _make_user(db_session, user_a)
    await _make_user(db_session, user_b)

    client_a = make_client(user_a)
    client_b = make_client(user_b)

    create_a = await client_a.post("/api/v1/workspaces", json={"name": f"ws-a-{unique_name}"})
    assert create_a.status_code == 201
    workspace_a_id = create_a.json()["id"]

    create_b = await client_b.post("/api/v1/workspaces", json={"name": f"ws-b-{unique_name}"})
    assert create_b.status_code == 201
    workspace_b_id = create_b.json()["id"]

    # user_a (member of A only) requests B's resource — must be 404, not
    # 403: existence of a workspace user_a isn't in must not leak.
    response = await client_a.get(f"/api/v1/workspaces/{workspace_b_id}")
    assert response.status_code == 404

    # Sanity: user_a CAN reach their own workspace A.
    own = await client_a.get(f"/api/v1/workspaces/{workspace_a_id}")
    assert own.status_code == 200


async def test_member_denied_owner_only_action_returns_403_and_is_audited(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"owner-{unique_name}"
    member = f"member-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, member)

    owner_client = make_client(owner)
    member_client = make_client(member)

    create = await owner_client.post("/api/v1/workspaces", json={"name": f"ws-{unique_name}"})
    workspace_id = create.json()["id"]

    invite = await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"user_id": member, "role": "member"},
    )
    assert invite.status_code == 201

    # member attempts an owner-only action (changing someone's role).
    denied = await member_client.patch(
        f"/api/v1/workspaces/{workspace_id}/members/{owner}",
        json={"role": "admin"},
    )
    assert denied.status_code == 403

    # The denial itself is written to audit_logs (CLAUDE.md §10 — from
    # the enforcement point, not left to the caller to remember).
    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.workspace_id == workspace_id,
            AuditLog.action == "permission.denied",
            AuditLog.actor_user_id == member,
        )
    )
    denial_entries = result.scalars().all()
    assert len(denial_entries) == 1
    assert denial_entries[0].outcome == "denied"


async def test_owner_can_change_member_role(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    owner = f"owner2-{unique_name}"
    member = f"member2-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, member)

    owner_client = make_client(owner)

    create = await owner_client.post("/api/v1/workspaces", json={"name": f"ws2-{unique_name}"})
    workspace_id = create.json()["id"]
    await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"user_id": member, "role": "member"},
    )

    response = await owner_client.patch(
        f"/api/v1/workspaces/{workspace_id}/members/{member}",
        json={"role": "admin"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
