"""Unit tests for the `execute_team` use case.

Focused on the paths the route tests deliberately don't cover: lock
contention, and the runnability guard that decides whether anything is
enqueued at all.
"""

from __future__ import annotations

from typing import Any

import pytest
from fakeredis.aioredis import FakeRedis
from tests.fakes.orchestration_repositories import FakeAgentRepository
from tests.fakes.team_repository import FakeTeamRepository

from agentverse_api.orchestration_service.application.execute_team import (
    TeamNotRunnableError,
    assert_runnable,
    execute_team,
    lock_key,
)
from agentverse_api.orchestration_service.domain.agent_entities import AgentConfig
from agentverse_api.orchestration_service.domain.run_exceptions import RunSubmissionConflictError
from agentverse_api.orchestration_service.domain.team_entities import (
    TeamMemberRole,
    TeamTopology,
)
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)

WORKSPACE_ID = "ws-1"
STREAM = "queue:jobs"


class NeverAcquiresLock:
    """Simulates a concurrent submission of the same key already holding
    the lock — the branch where this request must wait rather than race
    an insert.
    """

    async def acquire(self) -> bool:
        return False

    async def release(self) -> None:
        return None


class AlwaysAcquiresLock:
    async def acquire(self) -> bool:
        return True

    async def release(self) -> None:
        return None


async def _team_with_published_member(
    team_repo: FakeTeamRepository, agent_repo: FakeAgentRepository
) -> str:
    agent, version = await agent_repo.create_agent(
        workspace_id=WORKSPACE_ID,
        name="Researcher",
        description=None,
        created_by_user_id="user-1",
        initial_config=AgentConfig(model="gpt-4o-mini", system_instructions="Research."),
    )
    await agent_repo.publish_version(agent_id=agent.id, version_id=version.id)
    team = await team_repo.create_team(
        workspace_id=WORKSPACE_ID,
        name="Crew",
        description=None,
        topology=TeamTopology.SEQUENTIAL,
        objective=None,
        max_turns=20,
        max_cost_micro_usd=1_000_000,
        timeout_seconds=300,
        shared_memory_enabled=True,
        shared_knowledge_base_ids=[],
        created_by_user_id="user-1",
    )
    await team_repo.add_member(
        workspace_id=WORKSPACE_ID,
        team_id=team.id,
        agent_id=agent.id,
        role=TeamMemberRole.WORKER,
        position=0,
        handoff_description=None,
        can_receive_handoff=True,
    )
    return team.id


async def _execute(
    *, team_repo: Any, agent_repo: Any, redis: FakeRedis, team_id: str, lock: Any, key: str | None
) -> Any:
    return await execute_team(
        workspace_id=WORKSPACE_ID,
        team_id=team_id,
        input={"prompt": "Go."},
        idempotency_key=key,
        team_repo=team_repo,
        agent_repo=agent_repo,
        producer=JobQueueProducer(redis, stream=STREAM),
        lock_factory=lambda _k: lock,
    )


class TestLockKey:
    def test_is_scoped_by_workspace_and_team(self) -> None:
        """Two workspaces submitting the same Idempotency-Key must not
        collide — an unscoped key would let one tenant's submission
        suppress another's."""
        a = lock_key(workspace_id="ws-1", team_id="t-1", idempotency_key="k")
        b = lock_key(workspace_id="ws-2", team_id="t-1", idempotency_key="k")
        c = lock_key(workspace_id="ws-1", team_id="t-2", idempotency_key="k")
        assert len({a, b, c}) == 3


class TestRunnability:
    async def test_rejects_a_team_with_no_members(self) -> None:
        team_repo = FakeTeamRepository()
        team = await team_repo.create_team(
            workspace_id=WORKSPACE_ID,
            name="Empty",
            description=None,
            topology=TeamTopology.SEQUENTIAL,
            objective=None,
            max_turns=20,
            max_cost_micro_usd=1000,
            timeout_seconds=60,
            shared_memory_enabled=True,
            shared_knowledge_base_ids=[],
            created_by_user_id="user-1",
        )
        with pytest.raises(TeamNotRunnableError, match="no members"):
            await assert_runnable(team, agent_repo=FakeAgentRepository())

    async def test_accepts_a_team_where_one_member_is_published(self) -> None:
        """One published member is enough: the topology's own seat
        requirements are re-checked in the worker, and duplicating them
        here would create a second copy that can drift."""
        team_repo, agent_repo = FakeTeamRepository(), FakeAgentRepository()
        team_id = await _team_with_published_member(team_repo, agent_repo)
        team = await team_repo.get_team(workspace_id=WORKSPACE_ID, team_id=team_id)
        assert team is not None
        await assert_runnable(team, agent_repo=agent_repo)


class TestIdempotency:
    async def test_without_a_key_every_submission_creates_a_session(
        self, fake_redis: FakeRedis
    ) -> None:
        team_repo, agent_repo = FakeTeamRepository(), FakeAgentRepository()
        team_id = await _team_with_published_member(team_repo, agent_repo)
        first = await _execute(
            team_repo=team_repo,
            agent_repo=agent_repo,
            redis=fake_redis,
            team_id=team_id,
            lock=AlwaysAcquiresLock(),
            key=None,
        )
        second = await _execute(
            team_repo=team_repo,
            agent_repo=agent_repo,
            redis=fake_redis,
            team_id=team_id,
            lock=AlwaysAcquiresLock(),
            key=None,
        )
        assert first.id != second.id

    async def test_a_replayed_key_returns_the_original_without_re_enqueueing(
        self, fake_redis: FakeRedis
    ) -> None:
        team_repo, agent_repo = FakeTeamRepository(), FakeAgentRepository()
        team_id = await _team_with_published_member(team_repo, agent_repo)
        kwargs = {
            "team_repo": team_repo,
            "agent_repo": agent_repo,
            "redis": fake_redis,
            "team_id": team_id,
            "lock": AlwaysAcquiresLock(),
            "key": "k-1",
        }
        first = await _execute(**kwargs)
        second = await _execute(**kwargs)
        assert first.id == second.id
        assert len(await fake_redis.xrange(STREAM)) == 1

    async def test_losing_the_lock_with_no_visible_session_raises_conflict(
        self, fake_redis: FakeRedis
    ) -> None:
        """The concurrent holder never committed a session within the
        poll window. Raising beats creating a second one — a team session
        is expensive enough that a duplicate is a real cost."""
        team_repo, agent_repo = FakeTeamRepository(), FakeAgentRepository()
        team_id = await _team_with_published_member(team_repo, agent_repo)
        with pytest.raises(RunSubmissionConflictError):
            await _execute(
                team_repo=team_repo,
                agent_repo=agent_repo,
                redis=fake_redis,
                team_id=team_id,
                lock=NeverAcquiresLock(),
                key="k-1",
            )
        assert await fake_redis.xrange(STREAM) == []

    async def test_losing_the_lock_but_finding_the_session_returns_it(
        self, fake_redis: FakeRedis
    ) -> None:
        team_repo, agent_repo = FakeTeamRepository(), FakeAgentRepository()
        team_id = await _team_with_published_member(team_repo, agent_repo)
        # The concurrent holder's session, already committed.
        existing = await team_repo.create_session(
            workspace_id=WORKSPACE_ID, team_id=team_id, input={}, idempotency_key="k-1"
        )
        result = await _execute(
            team_repo=team_repo,
            agent_repo=agent_repo,
            redis=fake_redis,
            team_id=team_id,
            lock=NeverAcquiresLock(),
            key="k-1",
        )
        assert result.id == existing.id
        assert await fake_redis.xrange(STREAM) == []


class TestEnqueue:
    async def test_the_row_exists_before_the_job_is_enqueued(self, fake_redis: FakeRedis) -> None:
        """A job enqueued before its row exists can be picked up by a
        worker that finds nothing. The reverse leaves a visibly queued
        session that can be retried — the recoverable failure of the two.
        """
        team_repo, agent_repo = FakeTeamRepository(), FakeAgentRepository()
        team_id = await _team_with_published_member(team_repo, agent_repo)
        session = await _execute(
            team_repo=team_repo,
            agent_repo=agent_repo,
            redis=fake_redis,
            team_id=team_id,
            lock=AlwaysAcquiresLock(),
            key=None,
        )
        entries = await fake_redis.xrange(STREAM)
        assert session.id in entries[0][1]["payload"]
        assert (
            await team_repo.get_session(workspace_id=WORKSPACE_ID, session_id=session.id)
            is not None
        )
