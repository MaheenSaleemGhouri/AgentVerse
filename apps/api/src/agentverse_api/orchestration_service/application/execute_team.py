"""Idempotent team-session submission.

Deliberately the same shape as `run_agent`: check for an existing
session, take the distributed lock, re-check inside it, create, enqueue.
Two near-identical use cases would normally be a DRY violation, but they
guard different tables with different validity rules and merging them
would mean one function branching on "is this a team or an agent?" at
every step — the duplication here is in the sequence, not in the logic,
and consolidating it would couple the two lifecycles.

What differs is the validation: a team is runnable only if it has at
least one member whose agent is published, because a team of drafts
would enqueue a job that can only fail in the worker, minutes later,
after the user has been told it started.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from agentverse_api.orchestration_service.domain.ports.agent_repository import AgentRepository
from agentverse_api.orchestration_service.domain.ports.lock import Lock
from agentverse_api.orchestration_service.domain.ports.team_repository import TeamRepository
from agentverse_api.orchestration_service.domain.run_exceptions import RunSubmissionConflictError
from agentverse_api.orchestration_service.domain.team_entities import Team, TeamSession
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)

_POLL_ATTEMPTS = 5
_POLL_DELAY_SECONDS = 0.1

LockFactory = Callable[[str], Lock]


class TeamNotRunnableError(Exception):
    """The team cannot execute as configured.

    Raised before anything is enqueued, so the user learns why at
    submission time rather than from a failed session minutes later.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def lock_key(*, workspace_id: str, team_id: str, idempotency_key: str) -> str:
    return f"lock:team-session:{workspace_id}:{team_id}:{idempotency_key}"


async def assert_runnable(team: Team, *, agent_repo: AgentRepository) -> None:
    """Checks the team has members and that at least one is published.

    Topology-specific requirements (a supervisor for `supervisor_worker`,
    all three seats for `planner_executor_critic`) are re-checked in the
    worker where the topology actually executes. Checking the *cheap*
    conditions here and the topology conditions there is deliberate: this
    layer must not grow a second copy of the topology rules that can
    drift from the executor's.
    """
    if not team.members:
        raise TeamNotRunnableError(
            f"Team {team.name!r} has no members. Add at least one agent before running it."
        )
    for member in team.members:
        agent = await agent_repo.get_agent(workspace_id=team.workspace_id, agent_id=member.agent_id)
        if agent is not None and agent.published_version_id is not None:
            return
    raise TeamNotRunnableError(
        f"No member of team {team.name!r} has a published agent version. "
        "Publish at least one member's agent before running the team."
    )


async def execute_team(
    *,
    workspace_id: str,
    team_id: str,
    input: dict[str, Any],
    idempotency_key: str | None,
    team_repo: TeamRepository,
    agent_repo: AgentRepository,
    producer: JobQueueProducer,
    lock_factory: LockFactory,
) -> TeamSession:
    team = await team_repo.get_team(workspace_id=workspace_id, team_id=team_id)
    if team is None:
        raise TeamNotRunnableError("Team not found")
    await assert_runnable(team, agent_repo=agent_repo)

    if idempotency_key is None:
        return await _create_and_enqueue(
            workspace_id=workspace_id,
            team_id=team_id,
            input=input,
            idempotency_key=None,
            team_repo=team_repo,
            producer=producer,
        )

    existing = await team_repo.get_session_by_idempotency_key(
        workspace_id=workspace_id, team_id=team_id, idempotency_key=idempotency_key
    )
    if existing is not None:
        return existing

    lock = lock_factory(
        lock_key(workspace_id=workspace_id, team_id=team_id, idempotency_key=idempotency_key)
    )
    if not await lock.acquire():
        # A concurrent submission of this exact key is mid-flight. Wait
        # for it rather than racing an insert — a team session is
        # expensive enough that running two would be a real cost, not
        # just a duplicate row.
        polled = await _poll(team_repo, workspace_id, team_id, idempotency_key)
        if polled is not None:
            return polled
        raise RunSubmissionConflictError(idempotency_key)

    try:
        # Re-check inside the lock: closes the window between the check
        # above and actually holding it.
        existing = await team_repo.get_session_by_idempotency_key(
            workspace_id=workspace_id, team_id=team_id, idempotency_key=idempotency_key
        )
        if existing is not None:
            return existing
        return await _create_and_enqueue(
            workspace_id=workspace_id,
            team_id=team_id,
            input=input,
            idempotency_key=idempotency_key,
            team_repo=team_repo,
            producer=producer,
        )
    finally:
        await lock.release()


async def _poll(
    team_repo: TeamRepository, workspace_id: str, team_id: str, idempotency_key: str
) -> TeamSession | None:
    for _ in range(_POLL_ATTEMPTS):
        await asyncio.sleep(_POLL_DELAY_SECONDS)
        found = await team_repo.get_session_by_idempotency_key(
            workspace_id=workspace_id, team_id=team_id, idempotency_key=idempotency_key
        )
        if found is not None:
            return found
    return None


async def _create_and_enqueue(
    *,
    workspace_id: str,
    team_id: str,
    input: dict[str, Any],
    idempotency_key: str | None,
    team_repo: TeamRepository,
    producer: JobQueueProducer,
) -> TeamSession:
    """Row first, then enqueue.

    The order matters: a job enqueued before its row exists can be picked
    up by a worker that finds nothing and fails. The reverse — a row with
    no job — leaves a visibly queued session that can be retried, which
    is the recoverable failure of the two.
    """
    session = await team_repo.create_session(
        workspace_id=workspace_id,
        team_id=team_id,
        input=input,
        idempotency_key=idempotency_key,
    )
    await producer.enqueue(job_type="team_session", payload={"session_id": session.id})
    return session
