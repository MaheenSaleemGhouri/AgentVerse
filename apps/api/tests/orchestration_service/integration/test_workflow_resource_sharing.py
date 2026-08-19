"""Confirms `resource_type="workflow"` works end-to-end through the
existing generic `ResourcePermission` grant/list routes (Increment 6) —
Phase 10 Area E's entire scope, since the mechanism already exists and
`resource_type` is unrestricted free text (`Field(min_length=1,
max_length=50)`, no closed enum). No new backend code is needed; this
test is the proof, not a new capability under test.
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
            id=user_id, name=user_id, email=f"{user_id}@example.com", email_verified=False,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
    )
    await session.commit()


@pytest.fixture
async def make_client(db_session: AsyncSession) -> AsyncIterator[Callable[[str], AsyncClient]]:
    clients: list[AsyncClient] = []

    async def db_session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    def factory(user_id: str) -> AsyncClient:
        app = create_app()
        app.dependency_overrides[get_db_session] = db_session_override
        app.dependency_overrides[get_current_identity] = lambda: user_id
        app.dependency_overrides[get_current_identity_optional] = lambda: user_id
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        return client

    yield factory
    for client in clients:
        await client.aclose()


async def test_a_workflow_can_be_shared_with_a_teammate_via_the_generic_grant_route(
    db_session: AsyncSession, make_client: Callable[[str], AsyncClient], unique_name: str
) -> None:
    owner = f"wf-share-owner-{unique_name}"
    member = f"wf-share-member-{unique_name}"
    await _make_user(db_session, owner)
    await _make_user(db_session, member)

    owner_client = make_client(owner)
    member_client = make_client(member)

    create_ws = await owner_client.post(
        "/api/v1/workspaces", json={"name": f"wf-share-ws-{unique_name}"}
    )
    workspace_id = create_ws.json()["id"]
    await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"user_id": member, "role": "member"},
    )

    create_wf = await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        json={"name": "Shared Onboarding", "description": None},
    )
    assert create_wf.status_code == 201
    workflow_id = create_wf.json()["workflow"]["id"]

    grant = await owner_client.post(
        f"/api/v1/workspaces/{workspace_id}/resource-permissions",
        json={"resource_type": "workflow", "resource_id": workflow_id, "permission": "edit",
              "principal_id": member},
    )
    assert grant.status_code == 201
    assert grant.json()["resource_type"] == "workflow"
    assert grant.json()["resource_id"] == workflow_id

    listed = await owner_client.get(f"/api/v1/workspaces/{workspace_id}/resource-permissions")
    workflow_grants = [g for g in listed.json() if g["resource_type"] == "workflow"]
    assert len(workflow_grants) == 1
    assert workflow_grants[0]["principal_id"] == member

    # The grantee can still see the workflow through ordinary workspace
    # membership (viewing a workflow only ever required `require_viewer`)
    # — the grant is additive scope beyond the role floor, not a
    # replacement for it.
    fetched = await member_client.get(f"/api/v1/workspaces/{workspace_id}/workflows/{workflow_id}")
    assert fetched.status_code == 200
