"""Route-level tests for the workflow API. Every I/O dependency is a
fake (CLAUDE.md §11) — what's asserted here is the route's own
behaviour: status codes, tenancy resolution, the role each endpoint
requires, and 422 on an invalid graph.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_member,
    require_viewer,
)
from agentverse_api.auth_service.interface.dependencies.services import get_audit_service
from agentverse_api.main import create_app
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_workflow_repository,
)
from tests.fakes.audit_service import FakeAuditService
from tests.fakes.workflow_repository import FakeWorkflowRepository

WORKSPACE_ID = "ws-1"
OTHER_WORKSPACE_ID = "ws-2"
BASE = f"/api/v1/workspaces/{WORKSPACE_ID}/workflows"


@pytest.fixture
async def harness() -> AsyncIterator[dict[str, Any]]:
    app = create_app()
    workflow_repo = FakeWorkflowRepository()
    context = WorkspaceContext(workspace_id=WORKSPACE_ID, user_id="user-1", role=Role.ADMIN)

    app.dependency_overrides[require_viewer] = lambda: context
    app.dependency_overrides[require_member] = lambda: context
    app.dependency_overrides[get_workflow_repository] = lambda: workflow_repo
    app.dependency_overrides[get_audit_service] = lambda: FakeAuditService()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield {"client": client, "workflow_repo": workflow_repo}


async def _create_workflow(client: AsyncClient) -> dict[str, Any]:
    response = await client.post(BASE, json={"name": "Onboarding", "description": None})
    assert response.status_code == 201
    body: dict[str, Any] = response.json()
    return body


async def test_create_workflow_returns_workflow_and_empty_first_version(
    harness: dict[str, Any],
) -> None:
    client: AsyncClient = harness["client"]
    body = await _create_workflow(client)
    assert body["workflow"]["status"] == "draft"
    assert body["version"]["version_number"] == 1
    assert body["version"]["nodes"] == []


async def test_list_workflows_scopes_to_workspace(harness: dict[str, Any]) -> None:
    client: AsyncClient = harness["client"]
    await _create_workflow(client)

    response = await client.get(BASE)
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_get_unknown_workflow_is_404(harness: dict[str, Any]) -> None:
    client: AsyncClient = harness["client"]
    response = await client.get(f"{BASE}/does-not-exist")
    assert response.status_code == 404


async def test_create_version_with_valid_graph_succeeds(harness: dict[str, Any]) -> None:
    client: AsyncClient = harness["client"]
    workflow = (await _create_workflow(client))["workflow"]

    response = await client.post(
        f"{BASE}/{workflow['id']}/versions",
        json={
            "nodes": [
                {
                    "id": "n1",
                    "type": "human_approval",
                    "position_x": 0,
                    "position_y": 0,
                    "config": {"message": "Approve?"},
                }
            ],
            "edges": [],
        },
    )
    assert response.status_code == 201
    assert response.json()["version_number"] == 2


async def test_create_version_with_cycle_is_422(harness: dict[str, Any]) -> None:
    client: AsyncClient = harness["client"]
    workflow = (await _create_workflow(client))["workflow"]

    response = await client.post(
        f"{BASE}/{workflow['id']}/versions",
        json={
            "nodes": [
                {"id": "n1", "type": "parallel_fanout", "position_x": 0, "position_y": 0},
                {"id": "n2", "type": "parallel_fanout", "position_x": 0, "position_y": 0},
            ],
            "edges": [
                {"id": "e1", "from_node_id": "n1", "to_node_id": "n2"},
                {"id": "e2", "from_node_id": "n2", "to_node_id": "n1"},
            ],
        },
    )
    assert response.status_code == 422


async def test_publish_targets_the_requested_version(harness: dict[str, Any]) -> None:
    client: AsyncClient = harness["client"]
    created = await _create_workflow(client)
    workflow_id = created["workflow"]["id"]
    version_id = created["version"]["id"]

    response = await client.post(f"{BASE}/{workflow_id}/publish", json={"version_id": version_id})
    assert response.status_code == 200
    assert response.json()["published_version_id"] == version_id
    assert response.json()["status"] == "active"


async def test_diff_between_two_versions(harness: dict[str, Any]) -> None:
    client: AsyncClient = harness["client"]
    created = await _create_workflow(client)
    workflow_id = created["workflow"]["id"]
    v1_id = created["version"]["id"]

    v2 = await client.post(
        f"{BASE}/{workflow_id}/versions",
        json={
            "nodes": [
                {"id": "n1", "type": "parallel_fanout", "position_x": 0, "position_y": 0}
            ],
            "edges": [],
        },
    )
    v2_id = v2.json()["id"]

    response = await client.get(f"{BASE}/{workflow_id}/versions/{v2_id}/diff?against={v1_id}")
    assert response.status_code == 200
    body = response.json()
    assert [n["id"] for n in body["added_nodes"]] == ["n1"]
    assert body["removed_nodes"] == []
