"""Route-level tests for the team API.

Every I/O dependency is a fake (CLAUDE.md §11). What is asserted here is
the route's own behaviour: status codes, tenancy resolution, the role
each endpoint requires, and the guards that keep a misconfigured team
from being enqueued.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_admin,
    require_member,
    require_viewer,
)
from agentverse_api.main import create_app
from agentverse_api.orchestration_service.domain.agent_entities import AgentConfig
from agentverse_api.orchestration_service.domain.team_entities import TeamTopology
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_agent_repository,
    get_job_queue_producer,
    get_lock_factory,
    get_team_repository,
)
from tests.fakes.orchestration_repositories import FakeAgentRepository
from tests.fakes.team_repository import FakeTeamRepository

WORKSPACE_ID = "ws-1"
OTHER_WORKSPACE_ID = "ws-2"
STREAM = "queue:jobs"
BASE = f"/api/v1/workspaces/{WORKSPACE_ID}/teams"


class FakeLock:
    """Always acquires. The contended path is exercised directly against
    `execute_team` in the application-layer tests; a route test that also
    tried to simulate contention would be testing the lock, not the route.
    """

    async def acquire(self) -> bool:
        return True

    async def release(self) -> None:
        return None


@pytest.fixture
async def harness(fake_redis: FakeRedis) -> AsyncIterator[dict[str, Any]]:
    app = create_app()
    team_repo = FakeTeamRepository()
    agent_repo = FakeAgentRepository()
    context = WorkspaceContext(workspace_id=WORKSPACE_ID, user_id="user-1", role=Role.ADMIN)

    app.dependency_overrides[require_viewer] = lambda: context
    app.dependency_overrides[require_member] = lambda: context
    app.dependency_overrides[require_admin] = lambda: context
    app.dependency_overrides[get_team_repository] = lambda: team_repo
    app.dependency_overrides[get_agent_repository] = lambda: agent_repo
    app.dependency_overrides[get_lock_factory] = lambda: (lambda _key: FakeLock())
    app.dependency_overrides[get_job_queue_producer] = lambda: JobQueueProducer(
        fake_redis, stream=STREAM
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield {
            "client": client,
            "team_repo": team_repo,
            "agent_repo": agent_repo,
            "redis": fake_redis,
        }


async def _create_team(client: AsyncClient, topology: str = "sequential") -> str:
    response = await client.post(BASE, json={"name": "Research Crew", "topology": topology})
    assert response.status_code == 201
    team_id: str = response.json()["id"]
    return team_id


async def _published_agent(agent_repo: FakeAgentRepository, name: str = "Researcher") -> str:
    agent, version = await agent_repo.create_agent(
        workspace_id=WORKSPACE_ID,
        name=name,
        description=None,
        created_by_user_id="user-1",
        initial_config=AgentConfig(model="gpt-4o-mini", system_instructions="Research things."),
    )
    await agent_repo.publish_version(agent_id=agent.id, version_id=version.id)
    return agent.id


class TestTeamCrud:
    async def test_create_returns_201_with_defaults(self, harness: dict) -> None:
        response = await harness["client"].post(
            BASE, json={"name": "Research Crew", "topology": "supervisor_worker"}
        )
        assert response.status_code == 201
        body = response.json()
        assert body["workspace_id"] == WORKSPACE_ID
        assert body["topology"] == "supervisor_worker"
        # All three bounds are always present — a team without a cost or
        # time ceiling is not a valid team (Rule 17).
        assert body["max_turns"] > 0
        assert body["max_cost_micro_usd"] > 0
        assert body["timeout_seconds"] > 0

    async def test_rejects_an_unknown_topology(self, harness: dict) -> None:
        response = await harness["client"].post(BASE, json={"name": "X", "topology": "mesh"})
        assert response.status_code == 422

    async def test_patch_leaves_omitted_fields_alone(self, harness: dict) -> None:
        client: AsyncClient = harness["client"]
        team_id = await _create_team(client)
        response = await client.patch(f"{BASE}/{team_id}", json={"name": "Renamed"})
        assert response.status_code == 200
        assert response.json()["name"] == "Renamed"
        assert response.json()["topology"] == "sequential"

    async def test_patch_can_clear_a_nullable_field(self, harness: dict) -> None:
        """Sending null must clear `objective`, not be treated as
        "omitted" — otherwise clearing it would be impossible."""
        client: AsyncClient = harness["client"]
        response = await client.post(
            BASE, json={"name": "X", "topology": "sequential", "objective": "Do research."}
        )
        team_id = response.json()["id"]
        cleared = await client.patch(f"{BASE}/{team_id}", json={"objective": None})
        assert cleared.json()["objective"] is None

    async def test_delete_is_soft_and_removes_it_from_the_list(self, harness: dict) -> None:
        client: AsyncClient = harness["client"]
        team_id = await _create_team(client)
        assert (await client.delete(f"{BASE}/{team_id}")).status_code == 204
        assert (await client.get(f"{BASE}/{team_id}")).status_code == 404
        assert (await client.get(BASE)).json() == []

    async def test_duplicate_copies_config_and_seats_but_not_history(self, harness: dict) -> None:
        client: AsyncClient = harness["client"]
        agent_id = await _published_agent(harness["agent_repo"])
        team_id = await _create_team(client)
        await client.post(
            f"{BASE}/{team_id}/members", json={"agent_id": agent_id, "role": "researcher"}
        )

        response = await client.post(f"{BASE}/{team_id}/duplicate")
        assert response.status_code == 201
        copy = response.json()
        assert copy["id"] != team_id
        assert copy["name"].endswith("(copy)")
        # Seats point at the same agents — a team composes agents, it
        # never duplicates them.
        assert [m["agent_id"] for m in copy["members"]] == [agent_id]


class TestTenantIsolation:
    async def test_team_from_another_workspace_returns_404_not_403(self, harness: dict) -> None:
        """A 403 would confirm the team exists, leaking another tenant's
        resources by inference (CLAUDE.md §10)."""
        repo: FakeTeamRepository = harness["team_repo"]
        foreign = await repo.create_team(
            workspace_id=OTHER_WORKSPACE_ID,
            name="Someone else's crew",
            description=None,
            topology=TeamTopology.SEQUENTIAL,
            objective=None,
            max_turns=20,
            max_cost_micro_usd=1000,
            timeout_seconds=60,
            shared_memory_enabled=True,
            shared_knowledge_base_ids=[],
            created_by_user_id="user-9",
        )
        assert (await harness["client"].get(f"{BASE}/{foreign.id}")).status_code == 404

    async def test_list_only_returns_this_workspaces_teams(self, harness: dict) -> None:
        repo: FakeTeamRepository = harness["team_repo"]
        await _create_team(harness["client"])
        await repo.create_team(
            workspace_id=OTHER_WORKSPACE_ID,
            name="Other",
            description=None,
            topology=TeamTopology.SEQUENTIAL,
            objective=None,
            max_turns=20,
            max_cost_micro_usd=1000,
            timeout_seconds=60,
            shared_memory_enabled=True,
            shared_knowledge_base_ids=[],
            created_by_user_id="user-9",
        )
        body = (await harness["client"].get(BASE)).json()
        assert len(body) == 1
        assert body[0]["workspace_id"] == WORKSPACE_ID


class TestMembers:
    async def test_add_member_requires_an_existing_agent(self, harness: dict) -> None:
        client: AsyncClient = harness["client"]
        team_id = await _create_team(client)
        response = await client.post(
            f"{BASE}/{team_id}/members", json={"agent_id": "nope", "role": "worker"}
        )
        assert response.status_code == 404

    async def test_adding_the_same_agent_twice_is_a_409(self, harness: dict) -> None:
        """Mirrors the DB's `uq_team_member_agent` constraint with a
        readable message instead of letting an IntegrityError surface as
        a 500."""
        client: AsyncClient = harness["client"]
        agent_id = await _published_agent(harness["agent_repo"])
        team_id = await _create_team(client)
        payload = {"agent_id": agent_id, "role": "worker"}
        assert (await client.post(f"{BASE}/{team_id}/members", json=payload)).status_code == 201
        assert (await client.post(f"{BASE}/{team_id}/members", json=payload)).status_code == 409

    async def test_reorder_applies_drag_and_drop_order(self, harness: dict) -> None:
        client: AsyncClient = harness["client"]
        first = await _published_agent(harness["agent_repo"], "A")
        second = await _published_agent(harness["agent_repo"], "B")
        team_id = await _create_team(client)
        a = (
            await client.post(
                f"{BASE}/{team_id}/members",
                json={"agent_id": first, "role": "researcher", "position": 0},
            )
        ).json()
        b = (
            await client.post(
                f"{BASE}/{team_id}/members",
                json={"agent_id": second, "role": "writer", "position": 1},
            )
        ).json()

        response = await client.put(
            f"{BASE}/{team_id}/members/order", json={"member_ids": [b["id"], a["id"]]}
        )
        assert response.status_code == 200
        assert [m["agent_id"] for m in response.json()["members"]] == [second, first]

    async def test_partial_reorder_is_rejected(self, harness: dict) -> None:
        """A partial list would leave the omitted members at stale
        positions — for a `sequential` team that silently changes what
        runs when."""
        client: AsyncClient = harness["client"]
        first = await _published_agent(harness["agent_repo"], "A")
        await _published_agent(harness["agent_repo"], "B")
        team_id = await _create_team(client)
        a = (
            await client.post(
                f"{BASE}/{team_id}/members", json={"agent_id": first, "role": "researcher"}
            )
        ).json()
        second = await _published_agent(harness["agent_repo"], "C")
        await client.post(f"{BASE}/{team_id}/members", json={"agent_id": second, "role": "writer"})

        response = await client.put(
            f"{BASE}/{team_id}/members/order", json={"member_ids": [a["id"]]}
        )
        assert response.status_code == 400

    async def test_remove_member_returns_204(self, harness: dict) -> None:
        client: AsyncClient = harness["client"]
        agent_id = await _published_agent(harness["agent_repo"])
        team_id = await _create_team(client)
        member = (
            await client.post(
                f"{BASE}/{team_id}/members", json={"agent_id": agent_id, "role": "worker"}
            )
        ).json()
        assert (await client.delete(f"{BASE}/{team_id}/members/{member['id']}")).status_code == 204


class TestExecution:
    async def test_returns_202_and_enqueues_a_team_session_job(self, harness: dict) -> None:
        """Execution is a worker job, never inline in the request
        (Rule 14) — hence 202 with an id to poll, not 200 with a result."""
        client: AsyncClient = harness["client"]
        agent_id = await _published_agent(harness["agent_repo"])
        team_id = await _create_team(client)
        await client.post(
            f"{BASE}/{team_id}/members", json={"agent_id": agent_id, "role": "worker"}
        )

        response = await client.post(f"{BASE}/{team_id}/sessions", json={"prompt": "Summarise Q3."})
        assert response.status_code == 202
        assert response.json()["status"] == "queued"

        entries = await harness["redis"].xrange(STREAM)
        assert len(entries) == 1
        assert entries[0][1]["job_type"] == "team_session"

    async def test_team_with_no_members_is_rejected_before_enqueue(self, harness: dict) -> None:
        """The user learns why at submission time rather than from a
        failed session minutes later."""
        client: AsyncClient = harness["client"]
        team_id = await _create_team(client)
        response = await client.post(f"{BASE}/{team_id}/sessions", json={"prompt": "Go."})
        assert response.status_code == 409
        assert "no members" in response.json()["detail"].lower()
        assert await harness["redis"].xrange(STREAM) == []

    async def test_team_of_unpublished_agents_is_rejected(self, harness: dict) -> None:
        client: AsyncClient = harness["client"]
        agent, _ = await harness["agent_repo"].create_agent(
            workspace_id=WORKSPACE_ID,
            name="Draft",
            description=None,
            created_by_user_id="user-1",
            initial_config=AgentConfig(model="gpt-4o-mini", system_instructions="Draft."),
        )
        team_id = await _create_team(client)
        await client.post(
            f"{BASE}/{team_id}/members", json={"agent_id": agent.id, "role": "worker"}
        )
        response = await client.post(f"{BASE}/{team_id}/sessions", json={"prompt": "Go."})
        assert response.status_code == 409
        assert "publish" in response.json()["detail"].lower()

    async def test_replaying_an_idempotency_key_returns_the_same_session(
        self, harness: dict
    ) -> None:
        """A team session is expensive enough that running two would be a
        real cost, not just a duplicate row (Rule 14)."""
        client: AsyncClient = harness["client"]
        agent_id = await _published_agent(harness["agent_repo"])
        team_id = await _create_team(client)
        await client.post(
            f"{BASE}/{team_id}/members", json={"agent_id": agent_id, "role": "worker"}
        )
        headers = {"Idempotency-Key": "key-1"}

        first = await client.post(
            f"{BASE}/{team_id}/sessions", json={"prompt": "Go."}, headers=headers
        )
        second = await client.post(
            f"{BASE}/{team_id}/sessions", json={"prompt": "Go."}, headers=headers
        )

        assert first.json()["id"] == second.json()["id"]
        assert len(await harness["redis"].xrange(STREAM)) == 1

    async def test_empty_prompt_is_rejected(self, harness: dict) -> None:
        client: AsyncClient = harness["client"]
        team_id = await _create_team(client)
        response = await client.post(f"{BASE}/{team_id}/sessions", json={"prompt": ""})
        assert response.status_code == 422


class TestRuntimeReads:
    async def test_sessions_are_cursor_paginated(self, harness: dict) -> None:
        client: AsyncClient = harness["client"]
        repo: FakeTeamRepository = harness["team_repo"]
        team_id = await _create_team(client)
        for _ in range(3):
            await repo.create_session(
                workspace_id=WORKSPACE_ID, team_id=team_id, input={}, idempotency_key=None
            )

        page = (await client.get(f"{BASE}/{team_id}/sessions?limit=2")).json()
        assert len(page["data"]) == 2
        assert page["has_more"] is True
        assert page["next_cursor"] is not None

    async def test_events_endpoint_404s_for_an_unknown_session(self, harness: dict) -> None:
        client: AsyncClient = harness["client"]
        team_id = await _create_team(client)
        response = await client.get(f"{BASE}/{team_id}/sessions/missing/events")
        assert response.status_code == 404

    async def test_analytics_returns_integer_cents(self, harness: dict) -> None:
        """Money is integer micro-USD end to end (Rule 15) — a float
        here would be the first place it stopped being exact."""
        client: AsyncClient = harness["client"]
        team_id = await _create_team(client)
        body = (await client.get(f"{BASE}/{team_id}/analytics")).json()
        assert isinstance(body["total_cost_micro_usd"], int)
        assert isinstance(body["average_cost_micro_usd"], int)
        assert body["total_sessions"] == 0
