"""Route-level tests: request -> dependency-injected fakes -> response,
with the real DB session and Redis client both overridden (CLAUDE.md
§11 — no I/O in a unit test).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_member,
    require_viewer,
)
from agentverse_api.billing_service.application.quota_service import QuotaDecision
from agentverse_api.billing_service.domain.plan import MeteredDimension
from agentverse_api.billing_service.interface.dependencies.services import get_quota_service
from agentverse_api.main import create_app
from agentverse_api.orchestration_service.domain.agent_entities import AgentConfig
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_agent_repository,
    get_agent_run_repository,
    get_job_queue_producer,
    get_lock_factory,
)
from tests.fakes.orchestration_repositories import FakeAgentRepository, FakeAgentRunRepository

WORKSPACE_ID = "ws-1"
STREAM = "queue:jobs"


class _AlwaysAcquiresLock:
    async def acquire(self) -> bool:
        return True

    async def release(self) -> None:
        return None


def _lock_factory(_key: str) -> _AlwaysAcquiresLock:
    return _AlwaysAcquiresLock()


class _UnlimitedQuota:
    """Stands in for `QuotaService` with an unlimited allowance.

    Mirrors the real service's shape — `enforce` returns a decision and
    raises on refusal — so a route that started ignoring the decision
    would still be caught by the billing suite's own tests rather than
    passing here for the wrong reason.
    """

    async def enforce(
        self, *, workspace_id: str, dimension: MeteredDimension, requested: int = 1
    ) -> QuotaDecision:
        del workspace_id, requested
        return QuotaDecision(
            dimension=dimension,
            allowed=True,
            allowance=None,
            used=0,
            resets_at=datetime.now(UTC) + timedelta(days=30),
            billable_overage=False,
        )


@pytest.fixture
async def client_with_fakes(
    fake_redis: FakeRedis,
) -> AsyncIterator[tuple[AsyncClient, FakeAgentRepository, FakeAgentRunRepository]]:
    app = create_app()
    agent_repo = FakeAgentRepository()
    run_repo = FakeAgentRunRepository()
    context = WorkspaceContext(workspace_id=WORKSPACE_ID, user_id="user-1", role=Role.MEMBER)

    app.dependency_overrides[require_member] = lambda: context
    app.dependency_overrides[require_viewer] = lambda: context
    app.dependency_overrides[get_agent_repository] = lambda: agent_repo
    app.dependency_overrides[get_agent_run_repository] = lambda: run_repo
    app.dependency_overrides[get_job_queue_producer] = lambda: JobQueueProducer(
        fake_redis, stream=STREAM
    )
    app.dependency_overrides[get_lock_factory] = lambda: _lock_factory  # type: ignore[dict-item]
    # The run route enforces the metered agent-run quota before queuing.
    # This suite exercises run *submission* against fake repositories, so
    # the quota is stubbed to an unlimited plan — the enforcement itself
    # is covered in tests/billing_service, and leaving it wired here
    # would make every one of these tests depend on a real Postgres and
    # a seeded plan catalog.
    app.dependency_overrides[get_quota_service] = lambda: _UnlimitedQuota()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, agent_repo, run_repo


CREATE_BODY = {
    "name": "Support Triage Agent",
    "model": "gpt-4o-mini",
    "system_instructions": "Classify tickets by urgency.",
}


async def test_create_agent_returns_agent_and_first_version(
    client_with_fakes: tuple,
) -> None:
    client, _agent_repo, _run_repo = client_with_fakes

    response = await client.post(f"/api/v1/workspaces/{WORKSPACE_ID}/agents", json=CREATE_BODY)

    assert response.status_code == 201
    body = response.json()
    assert body["agent"]["name"] == "Support Triage Agent"
    assert body["agent"]["status"] == "draft"
    assert body["version"]["version_number"] == 1


async def test_get_agent_not_found_returns_404(client_with_fakes: tuple) -> None:
    client, _agent_repo, _run_repo = client_with_fakes

    response = await client.get(f"/api/v1/workspaces/{WORKSPACE_ID}/agents/does-not-exist")

    assert response.status_code == 404


async def test_run_rejects_unpublished_agent_with_409(client_with_fakes: tuple) -> None:
    client, agent_repo, _run_repo = client_with_fakes
    agent, _version = await agent_repo.create_agent(
        workspace_id=WORKSPACE_ID,
        name="Draft",
        description=None,
        created_by_user_id="user-1",
        initial_config=AgentConfig(model="gpt-4o-mini", system_instructions="x"),
    )

    response = await client.post(
        f"/api/v1/workspaces/{WORKSPACE_ID}/agents/{agent.id}/runs", json={"input": {}}
    )

    assert response.status_code == 409


async def test_publish_then_run_succeeds_and_enqueues(
    client_with_fakes: tuple, fake_redis: FakeRedis
) -> None:
    client, agent_repo, _run_repo = client_with_fakes
    agent, _version = await agent_repo.create_agent(
        workspace_id=WORKSPACE_ID,
        name="Publishable",
        description=None,
        created_by_user_id="user-1",
        initial_config=AgentConfig(model="gpt-4o-mini", system_instructions="x"),
    )

    publish_response = await client.post(
        f"/api/v1/workspaces/{WORKSPACE_ID}/agents/{agent.id}/publish"
    )
    assert publish_response.status_code == 200
    assert publish_response.json()["status"] == "active"

    run_response = await client.post(
        f"/api/v1/workspaces/{WORKSPACE_ID}/agents/{agent.id}/runs",
        json={"input": {"prompt": "hello"}},
    )

    assert run_response.status_code == 202
    assert run_response.json()["status"] == "queued"
    assert await fake_redis.xlen(STREAM) == 1


async def test_get_latest_version_returns_current_config(client_with_fakes: tuple) -> None:
    client, agent_repo, _run_repo = client_with_fakes
    agent, version = await agent_repo.create_agent(
        workspace_id=WORKSPACE_ID,
        name="Versioned",
        description=None,
        created_by_user_id="user-1",
        initial_config=AgentConfig(model="gpt-4o-mini", system_instructions="v1"),
    )

    response = await client.get(
        f"/api/v1/workspaces/{WORKSPACE_ID}/agents/{agent.id}/versions/latest"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == version.id
    assert body["version_number"] == 1
    assert body["system_instructions"] == "v1"


async def test_get_latest_version_404s_for_unknown_agent(client_with_fakes: tuple) -> None:
    client, _agent_repo, _run_repo = client_with_fakes

    response = await client.get(
        f"/api/v1/workspaces/{WORKSPACE_ID}/agents/does-not-exist/versions/latest"
    )

    assert response.status_code == 404


async def test_create_version_bumps_version_number_and_updates_config(
    client_with_fakes: tuple,
) -> None:
    client, agent_repo, _run_repo = client_with_fakes
    agent, _version = await agent_repo.create_agent(
        workspace_id=WORKSPACE_ID,
        name="Editable",
        description=None,
        created_by_user_id="user-1",
        initial_config=AgentConfig(model="gpt-4o-mini", system_instructions="v1"),
    )

    response = await client.post(
        f"/api/v1/workspaces/{WORKSPACE_ID}/agents/{agent.id}/versions",
        json={
            "model": "gpt-4o-mini",
            "system_instructions": "v2 — revised instructions",
            "tools": ["calculator"],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["version_number"] == 2
    assert body["system_instructions"] == "v2 — revised instructions"
    assert body["tools"] == ["calculator"]

    latest = await agent_repo.get_latest_version(agent_id=agent.id)
    assert latest is not None
    assert latest.version_number == 2


async def test_create_version_404s_for_unknown_agent(client_with_fakes: tuple) -> None:
    client, _agent_repo, _run_repo = client_with_fakes

    response = await client.post(
        f"/api/v1/workspaces/{WORKSPACE_ID}/agents/does-not-exist/versions",
        json={"model": "gpt-4o-mini", "system_instructions": "x"},
    )

    assert response.status_code == 404


async def test_replayed_idempotency_key_header_returns_same_run(
    client_with_fakes: tuple, fake_redis: FakeRedis
) -> None:
    client, agent_repo, _run_repo = client_with_fakes
    agent, version = await agent_repo.create_agent(
        workspace_id=WORKSPACE_ID,
        name="Idempotent",
        description=None,
        created_by_user_id="user-1",
        initial_config=AgentConfig(model="gpt-4o-mini", system_instructions="x"),
    )
    await agent_repo.publish_version(agent_id=agent.id, version_id=version.id)

    headers = {"Idempotency-Key": "replay-key-1"}
    first = await client.post(
        f"/api/v1/workspaces/{WORKSPACE_ID}/agents/{agent.id}/runs",
        json={"input": {}},
        headers=headers,
    )
    second = await client.post(
        f"/api/v1/workspaces/{WORKSPACE_ID}/agents/{agent.id}/runs",
        json={"input": {}},
        headers=headers,
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert await fake_redis.xlen(STREAM) == 1
