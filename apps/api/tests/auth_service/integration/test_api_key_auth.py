"""API keys as real bearer credentials, end-to-end through the app and
real Postgres.

Until this suite existed, `api_keys.hashed_key` was written but never
read on any request path — issuing a key granted nothing. These tests
pin the three properties that make it a credential rather than a
decoration: it authenticates, it is capped by its scope, and it cannot
reach past its own workspace.

Unlike the sibling RBAC suite, `get_current_identity` is deliberately
*not* overridden for the key-bearing clients — the whole point is to
exercise real credential resolution.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
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
    """Two client factories over one app: `as_user(...)` stubs a session
    the way the RBAC suite does, and `as_key_bearer()` stubs nothing —
    it authenticates purely by the `Authorization` header it is given.
    """
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

    def as_key_bearer() -> AsyncClient:
        app = create_app()
        app.dependency_overrides[get_db_session] = db_session_override
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        opened.append(client)
        return client

    yield as_user, as_key_bearer

    for client in opened:
        await client.aclose()


async def _workspace_with_key(
    owner_client: AsyncClient, *, name: str, scope: str
) -> tuple[str, str]:
    created = await owner_client.post("/api/v1/workspaces", json={"name": name})
    workspace_id = created.json()["id"]
    issued = await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/api-keys",
        json={"name": f"{name}-key", "scope": scope},
    )
    assert issued.status_code == 201, issued.text
    return workspace_id, issued.json()["key"]


async def test_a_full_scope_key_authenticates_a_real_request(
    db_session: AsyncSession,
    clients: tuple[Callable[[str], AsyncClient], Callable[[], AsyncClient]],
    unique_name: str,
) -> None:
    as_user, as_key_bearer = clients
    owner = f"key-owner-{unique_name}"
    await _make_user(db_session, owner)

    workspace_id, plaintext = await _workspace_with_key(
        as_user(owner), name=f"key-ws-{unique_name}", scope="full"
    )

    response = await as_key_bearer().get(
        f"/api/v1/workspaces/{workspace_id}/members",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert response.status_code == 200
    assert any(member["user_id"] == owner for member in response.json())


async def test_a_read_only_key_is_capped_at_viewer(
    db_session: AsyncSession,
    clients: tuple[Callable[[str], AsyncClient], Callable[[], AsyncClient]],
    unique_name: str,
) -> None:
    as_user, as_key_bearer = clients
    owner = f"ro-owner-{unique_name}"
    await _make_user(db_session, owner)

    workspace_id, plaintext = await _workspace_with_key(
        as_user(owner), name=f"ro-ws-{unique_name}", scope="read_only"
    )
    key_client = as_key_bearer()
    auth = {"Authorization": f"Bearer {plaintext}"}

    # Viewer-level reads still work…
    readable = await key_client.get(f"/api/v1/workspaces/{workspace_id}/members", headers=auth)
    assert readable.status_code == 200

    # …but the admin-gated write is refused, even though the key was
    # issued by the workspace *owner*.
    denied = await key_client.post(
        f"/api/v1/workspaces/{workspace_id}/api-keys",
        json={"name": "escalated"},
        headers=auth,
    )
    assert denied.status_code == 403


async def test_a_key_cannot_reach_another_workspace(
    db_session: AsyncSession,
    clients: tuple[Callable[[str], AsyncClient], Callable[[], AsyncClient]],
    unique_name: str,
) -> None:
    as_user, as_key_bearer = clients
    owner = f"x-owner-{unique_name}"
    await _make_user(db_session, owner)
    owner_client = as_user(owner)

    _, plaintext = await _workspace_with_key(
        owner_client, name=f"x-ws-a-{unique_name}", scope="full"
    )
    other = await owner_client.post("/api/v1/workspaces", json={"name": f"x-ws-b-{unique_name}"})
    other_id = other.json()["id"]

    # Same human owns both workspaces, but the key is scoped to one —
    # and the other must be indistinguishable from nonexistent.
    response = await as_key_bearer().get(
        f"/api/v1/workspaces/{other_id}/members",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert response.status_code == 404


async def test_a_revoked_key_stops_authenticating(
    db_session: AsyncSession,
    clients: tuple[Callable[[str], AsyncClient], Callable[[], AsyncClient]],
    unique_name: str,
) -> None:
    as_user, as_key_bearer = clients
    owner = f"rev-owner-{unique_name}"
    await _make_user(db_session, owner)
    owner_client = as_user(owner)

    workspace_id, plaintext = await _workspace_with_key(
        owner_client, name=f"rev-ws-{unique_name}", scope="full"
    )
    listed = await owner_client.get(f"/api/v1/workspaces/{workspace_id}/api-keys")
    key_id = listed.json()[0]["id"]

    key_client = as_key_bearer()
    auth = {"Authorization": f"Bearer {plaintext}"}
    assert (
        await key_client.get(f"/api/v1/workspaces/{workspace_id}/members", headers=auth)
    ).status_code == 200

    revoked = await owner_client.delete(f"/api/v1/workspaces/{workspace_id}/api-keys/{key_id}")
    assert revoked.status_code == 204

    after = await key_client.get(f"/api/v1/workspaces/{workspace_id}/members", headers=auth)
    assert after.status_code == 401


async def test_an_unknown_key_is_rejected_without_leaking_why(
    clients: tuple[Callable[[str], AsyncClient], Callable[[], AsyncClient]],
) -> None:
    _, as_key_bearer = clients
    response = await as_key_bearer().get(
        "/api/v1/workspaces/00000000-0000-0000-0000-000000000000/members",
        headers={"Authorization": "Bearer av_live_not-a-real-key"},
    )
    assert response.status_code == 401
    assert "revoked" in response.json()["detail"] or "Invalid" in response.json()["detail"]


async def test_an_api_key_cannot_act_on_user_session_surfaces(
    db_session: AsyncSession,
    clients: tuple[Callable[[str], AsyncClient], Callable[[], AsyncClient]],
    unique_name: str,
) -> None:
    """A workspace-scoped key must not become its issuer: listing or
    creating workspaces would let it reach every *other* workspace that
    human belongs to.
    """
    as_user, as_key_bearer = clients
    owner = f"sess-owner-{unique_name}"
    await _make_user(db_session, owner)

    _, plaintext = await _workspace_with_key(
        as_user(owner), name=f"sess-ws-{unique_name}", scope="full"
    )
    response = await as_key_bearer().get(
        "/api/v1/workspaces", headers={"Authorization": f"Bearer {plaintext}"}
    )
    assert response.status_code == 401
