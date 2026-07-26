"""Idempotent run-submission use case (docs/roadmap.md Phase 4):
validates the agent has a published version, dedupes on
`Idempotency-Key` using Phase 3's distributed lock as the *primary*
mechanism, and enqueues the run job (CLAUDE.md Rule 14: long-running
execution is never inline in a request).

Only the lock holder ever calls `run_repo.create_run` — a non-holder
takes the polling branch instead of racing an insert. The DB's partial
unique index on `(workspace_id, idempotency_key)` (see the Phase 4
migration) is still a real constraint, but it is defense-in-depth: this
use case's own logic never attempts a duplicate insert, so that index
is not expected to actually reject anything under normal operation —
if it ever did, that would indicate a bug elsewhere, not a condition
this function papers over.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from agentverse_api.orchestration_service.domain.agent_entities import AgentVersion
from agentverse_api.orchestration_service.domain.ports.agent_repository import AgentRepository
from agentverse_api.orchestration_service.domain.ports.lock import Lock
from agentverse_api.orchestration_service.domain.ports.run_repository import AgentRunRepository
from agentverse_api.orchestration_service.domain.run_entities import AgentRun
from agentverse_api.orchestration_service.domain.run_exceptions import (
    AgentNotRunnableError,
    RunSubmissionConflictError,
)
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)

_POLL_ATTEMPTS = 5
_POLL_DELAY_SECONDS = 0.1

LockFactory = Callable[[str], Lock]


def lock_key(*, workspace_id: str, idempotency_key: str) -> str:
    return f"lock:agent-run:{workspace_id}:{idempotency_key}"


async def run_agent(
    *,
    workspace_id: str,
    agent_id: str,
    input: dict[str, Any],
    idempotency_key: str | None,
    agent_repo: AgentRepository,
    run_repo: AgentRunRepository,
    producer: JobQueueProducer,
    lock_factory: LockFactory,
) -> AgentRun:
    if idempotency_key is None:
        return await _create_and_enqueue(
            workspace_id=workspace_id,
            agent_id=agent_id,
            input=input,
            idempotency_key=None,
            agent_repo=agent_repo,
            run_repo=run_repo,
            producer=producer,
        )

    existing = await run_repo.get_run_by_idempotency_key(
        workspace_id=workspace_id, idempotency_key=idempotency_key
    )
    if existing is not None:
        return existing

    lock = lock_factory(lock_key(workspace_id=workspace_id, idempotency_key=idempotency_key))
    if not await lock.acquire():
        # A concurrent request for this exact idempotency key is already
        # mid-flight — wait for it to finish rather than racing an insert.
        polled = await _poll_for_run(run_repo, workspace_id, idempotency_key)
        if polled is not None:
            return polled
        raise RunSubmissionConflictError(idempotency_key)

    try:
        # Re-check inside the lock: closes the race window between the
        # check above and actually acquiring it.
        existing = await run_repo.get_run_by_idempotency_key(
            workspace_id=workspace_id, idempotency_key=idempotency_key
        )
        if existing is not None:
            return existing
        return await _create_and_enqueue(
            workspace_id=workspace_id,
            agent_id=agent_id,
            input=input,
            idempotency_key=idempotency_key,
            agent_repo=agent_repo,
            run_repo=run_repo,
            producer=producer,
        )
    finally:
        await lock.release()


async def _resolve_runnable_version(
    *, workspace_id: str, agent_id: str, agent_repo: AgentRepository
) -> AgentVersion:
    agent = await agent_repo.get_agent(workspace_id=workspace_id, agent_id=agent_id)
    if agent is None or agent.published_version_id is None:
        raise AgentNotRunnableError(agent_id)
    version = await agent_repo.get_version(agent_id=agent_id, version_id=agent.published_version_id)
    if version is None:
        raise AgentNotRunnableError(agent_id)
    return version


async def _create_and_enqueue(
    *,
    workspace_id: str,
    agent_id: str,
    input: dict[str, Any],
    idempotency_key: str | None,
    agent_repo: AgentRepository,
    run_repo: AgentRunRepository,
    producer: JobQueueProducer,
) -> AgentRun:
    version = await _resolve_runnable_version(
        workspace_id=workspace_id, agent_id=agent_id, agent_repo=agent_repo
    )
    run = await run_repo.create_run(
        workspace_id=workspace_id,
        agent_id=agent_id,
        agent_version_id=version.id,
        input=input,
        idempotency_key=idempotency_key,
    )
    await producer.enqueue_agent_run(run_id=run.id)
    return run


async def _poll_for_run(
    run_repo: AgentRunRepository, workspace_id: str, idempotency_key: str
) -> AgentRun | None:
    for _ in range(_POLL_ATTEMPTS):
        existing = await run_repo.get_run_by_idempotency_key(
            workspace_id=workspace_id, idempotency_key=idempotency_key
        )
        if existing is not None:
            return existing
        await asyncio.sleep(_POLL_DELAY_SECONDS)
    return None
