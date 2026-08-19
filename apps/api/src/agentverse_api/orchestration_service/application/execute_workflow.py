"""Idempotent workflow-run submission use case — the exact same shape as
`run_agent.py`/`execute_team.py`: dedupe on `Idempotency-Key` using the
distributed lock as the primary mechanism, create the row, enqueue the
start node(s)' jobs (never inline execution — Rule 14).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from agentverse_api.orchestration_service.domain.ports.lock import Lock
from agentverse_api.orchestration_service.domain.ports.workflow_repository import (
    WorkflowRepository,
)
from agentverse_api.orchestration_service.domain.ports.workflow_run_repository import (
    WorkflowRunRepository,
)
from agentverse_api.orchestration_service.domain.run_exceptions import RunSubmissionConflictError
from agentverse_api.orchestration_service.domain.workflow_entities import WorkflowRun
from agentverse_api.orchestration_service.domain.workflow_exceptions import (
    WorkflowNotRunnableError,
)
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)

_POLL_ATTEMPTS = 5
_POLL_DELAY_SECONDS = 0.1

LockFactory = Callable[[str], Lock]


def lock_key(*, workspace_id: str, workflow_id: str, idempotency_key: str) -> str:
    return f"lock:workflow-run:{workspace_id}:{workflow_id}:{idempotency_key}"


async def execute_workflow(
    *,
    workspace_id: str,
    workflow_id: str,
    input: dict[str, Any],
    idempotency_key: str | None,
    workflow_repo: WorkflowRepository,
    run_repo: WorkflowRunRepository,
    producer: JobQueueProducer,
    lock_factory: LockFactory,
) -> WorkflowRun:
    workflow = await workflow_repo.get_workflow(workspace_id=workspace_id, workflow_id=workflow_id)
    if workflow is None or workflow.published_version_id is None:
        raise WorkflowNotRunnableError(workflow_id)
    version = await workflow_repo.get_version(
        workflow_id=workflow_id, version_id=workflow.published_version_id
    )
    if version is None or not version.start_nodes():
        raise WorkflowNotRunnableError(workflow_id)

    if idempotency_key is None:
        return await _create_and_enqueue(
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            version_id=version.id,
            start_node_ids=[n.id for n in version.start_nodes()],
            input=input,
            idempotency_key=None,
            run_repo=run_repo,
            producer=producer,
        )

    existing = await run_repo.get_run_by_idempotency_key(
        workflow_id=workflow_id, idempotency_key=idempotency_key
    )
    if existing is not None:
        return existing

    lock = lock_factory(
        lock_key(
            workspace_id=workspace_id, workflow_id=workflow_id, idempotency_key=idempotency_key
        )
    )
    if not await lock.acquire():
        polled = await _poll(run_repo, workflow_id, idempotency_key)
        if polled is not None:
            return polled
        raise RunSubmissionConflictError(idempotency_key)

    try:
        existing = await run_repo.get_run_by_idempotency_key(
            workflow_id=workflow_id, idempotency_key=idempotency_key
        )
        if existing is not None:
            return existing
        return await _create_and_enqueue(
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            version_id=version.id,
            start_node_ids=[n.id for n in version.start_nodes()],
            input=input,
            idempotency_key=idempotency_key,
            run_repo=run_repo,
            producer=producer,
        )
    finally:
        await lock.release()


async def _poll(
    run_repo: WorkflowRunRepository, workflow_id: str, idempotency_key: str
) -> WorkflowRun | None:
    for _ in range(_POLL_ATTEMPTS):
        await asyncio.sleep(_POLL_DELAY_SECONDS)
        found = await run_repo.get_run_by_idempotency_key(
            workflow_id=workflow_id, idempotency_key=idempotency_key
        )
        if found is not None:
            return found
    return None


async def _create_and_enqueue(
    *,
    workspace_id: str,
    workflow_id: str,
    version_id: str,
    start_node_ids: list[str],
    input: dict[str, Any],
    idempotency_key: str | None,
    run_repo: WorkflowRunRepository,
    producer: JobQueueProducer,
) -> WorkflowRun:
    """Row first, then enqueue — same ordering discipline as `run_agent.
    py`/`execute_team.py`: a job enqueued before its row exists can be
    picked up by a worker that finds nothing and fails.
    """
    run = await run_repo.create_run(
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        workflow_version_id=version_id,
        input=input,
        idempotency_key=idempotency_key,
    )
    for node_id in start_node_ids:
        await producer.enqueue(
            job_type="workflow_node", payload={"workflow_run_id": run.id, "node_id": node_id}
        )
    return run
