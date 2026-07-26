"""Exercises docs/roadmap.md Phase 4's run-submission acceptance
criteria directly: a runnable agent enqueues a job without inline
blocking, an unrunnable agent is rejected, and a replayed
Idempotency-Key returns the original run without creating a second one
or enqueuing twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from fakeredis.aioredis import FakeRedis
from tests.fakes.orchestration_repositories import FakeAgentRepository, FakeAgentRunRepository

from agentverse_api.orchestration_service.application.run_agent import run_agent
from agentverse_api.orchestration_service.domain.agent_entities import AgentConfig
from agentverse_api.orchestration_service.domain.run_exceptions import (
    AgentNotRunnableError,
    RunSubmissionConflictError,
)
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)

WORKSPACE_ID = "ws-1"
STREAM = "queue:jobs"


@dataclass
class FakeLock:
    should_acquire: bool = True
    acquire_called: bool = False
    released: bool = False

    async def acquire(self) -> bool:
        self.acquire_called = True
        return self.should_acquire

    async def release(self) -> None:
        self.released = True


@dataclass
class RecordingLockFactory:
    should_acquire: bool = True
    locks: list[FakeLock] = field(default_factory=list)

    def __call__(self, key: str) -> FakeLock:
        lock = FakeLock(should_acquire=self.should_acquire)
        self.locks.append(lock)
        return lock


async def _make_runnable_agent(agent_repo: FakeAgentRepository) -> str:
    agent, version = await agent_repo.create_agent(
        workspace_id=WORKSPACE_ID,
        name="Support Agent",
        description=None,
        created_by_user_id="user-1",
        initial_config=AgentConfig(model="gpt-4o-mini", system_instructions="Be helpful."),
    )
    await agent_repo.publish_version(agent_id=agent.id, version_id=version.id)
    return agent.id


@pytest.fixture
async def producer(fake_redis: FakeRedis) -> JobQueueProducer:
    return JobQueueProducer(fake_redis, stream=STREAM)


async def test_run_without_idempotency_key_always_creates_a_new_run(
    fake_redis: FakeRedis, producer: JobQueueProducer
) -> None:
    agent_repo = FakeAgentRepository()
    run_repo = FakeAgentRunRepository()
    agent_id = await _make_runnable_agent(agent_repo)
    lock_factory = RecordingLockFactory()

    run_a = await run_agent(
        workspace_id=WORKSPACE_ID,
        agent_id=agent_id,
        input={"prompt": "hi"},
        idempotency_key=None,
        agent_repo=agent_repo,
        run_repo=run_repo,
        producer=producer,
        lock_factory=lock_factory,
    )
    run_b = await run_agent(
        workspace_id=WORKSPACE_ID,
        agent_id=agent_id,
        input={"prompt": "hi"},
        idempotency_key=None,
        agent_repo=agent_repo,
        run_repo=run_repo,
        producer=producer,
        lock_factory=lock_factory,
    )

    assert run_a.id != run_b.id
    assert len(lock_factory.locks) == 0  # no dedup requested, no lock ever touched
    assert await fake_redis.xlen(STREAM) == 2


async def test_run_rejects_agent_with_no_published_version(
    producer: JobQueueProducer,
) -> None:
    agent_repo = FakeAgentRepository()
    run_repo = FakeAgentRunRepository()
    agent, _version = await agent_repo.create_agent(
        workspace_id=WORKSPACE_ID,
        name="Draft Agent",
        description=None,
        created_by_user_id="user-1",
        initial_config=AgentConfig(model="gpt-4o-mini", system_instructions="Be helpful."),
    )

    with pytest.raises(AgentNotRunnableError):
        await run_agent(
            workspace_id=WORKSPACE_ID,
            agent_id=agent.id,
            input={},
            idempotency_key=None,
            agent_repo=agent_repo,
            run_repo=run_repo,
            producer=producer,
            lock_factory=RecordingLockFactory(),
        )


async def test_replayed_idempotency_key_returns_original_run_without_second_enqueue(
    fake_redis: FakeRedis, producer: JobQueueProducer
) -> None:
    agent_repo = FakeAgentRepository()
    run_repo = FakeAgentRunRepository()
    agent_id = await _make_runnable_agent(agent_repo)
    lock_factory = RecordingLockFactory()

    first = await run_agent(
        workspace_id=WORKSPACE_ID,
        agent_id=agent_id,
        input={"prompt": "hi"},
        idempotency_key="idem-123",
        agent_repo=agent_repo,
        run_repo=run_repo,
        producer=producer,
        lock_factory=lock_factory,
    )
    second = await run_agent(
        workspace_id=WORKSPACE_ID,
        agent_id=agent_id,
        input={"prompt": "hi"},
        idempotency_key="idem-123",
        agent_repo=agent_repo,
        run_repo=run_repo,
        producer=producer,
        lock_factory=lock_factory,
    )

    assert first.id == second.id
    assert await fake_redis.xlen(STREAM) == 1  # only the first call ever enqueued
    # Second call found the existing run via the plain lookup — never
    # even reached for a lock.
    assert len(lock_factory.locks) == 1


async def test_concurrent_request_polls_instead_of_double_enqueueing(
    fake_redis: FakeRedis, producer: JobQueueProducer
) -> None:
    """Simulates: another request already holds the lock for this exact
    idempotency key and is mid-flight. This request must not attempt to
    create a second run — it polls until the row appears.
    """
    agent_repo = FakeAgentRepository()
    run_repo = FakeAgentRunRepository()
    agent_id = await _make_runnable_agent(agent_repo)

    # Pre-seed the run the "other request" is presumed to be creating,
    # landing partway through this call's bounded poll window.
    existing = await run_repo.create_run(
        workspace_id=WORKSPACE_ID,
        agent_id=agent_id,
        agent_version_id=(await agent_repo.get_latest_version(agent_id=agent_id)).id,  # type: ignore[union-attr]
        input={"prompt": "hi"},
        idempotency_key="idem-concurrent",
    )

    lock_factory = RecordingLockFactory(should_acquire=False)

    result = await run_agent(
        workspace_id=WORKSPACE_ID,
        agent_id=agent_id,
        input={"prompt": "hi"},
        idempotency_key="idem-concurrent",
        agent_repo=agent_repo,
        run_repo=run_repo,
        producer=producer,
        lock_factory=lock_factory,
    )

    assert result.id == existing.id
    assert await fake_redis.xlen(STREAM) == 0  # this request never enqueued anything


async def test_conflict_raised_if_lock_holder_never_produces_a_run(
    producer: JobQueueProducer,
) -> None:
    agent_repo = FakeAgentRepository()
    run_repo = FakeAgentRunRepository()
    agent_id = await _make_runnable_agent(agent_repo)
    lock_factory = RecordingLockFactory(should_acquire=False)

    with pytest.raises(RunSubmissionConflictError):
        await run_agent(
            workspace_id=WORKSPACE_ID,
            agent_id=agent_id,
            input={},
            idempotency_key="idem-never-appears",
            agent_repo=agent_repo,
            run_repo=run_repo,
            producer=producer,
            lock_factory=lock_factory,
        )
