"""Resolves a `human_approval` node's durable pause — this route *is*
the resume mechanism (docs/adr/0016): no separate scheduler polls for
approvals. Approval writes the decision to the paused
`workflow_node_runs` row (a plain Postgres row, not anything held in
worker memory, so the pause survives a worker restart by construction)
and, if approved, enqueues the node's outgoing edges exactly like a
normal terminal-success advance.
"""

from __future__ import annotations

from typing import Literal

from agentverse_api.orchestration_service.domain.ports.workflow_repository import (
    WorkflowRepository,
)
from agentverse_api.orchestration_service.domain.ports.workflow_run_repository import (
    WorkflowRunRepository,
)
from agentverse_api.orchestration_service.domain.workflow_entities import WorkflowNodeRun
from agentverse_api.orchestration_service.domain.workflow_exceptions import (
    WorkflowNotRunnableError,
)
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)


class NodeNotPausedError(Exception):
    """The node isn't currently waiting on approval — either it hasn't
    run yet, already resolved, or isn't a `human_approval` node at all.
    Maps to 409: the caller's view of the run is stale.
    """

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        super().__init__(f"Node {node_id!r} is not awaiting approval")


async def resolve_workflow_approval(
    *,
    workspace_id: str,
    workflow_id: str,
    run_id: str,
    node_id: str,
    decision: Literal["approved", "rejected"],
    approved_by_user_id: str,
    workflow_repo: WorkflowRepository,
    run_repo: WorkflowRunRepository,
    producer: JobQueueProducer,
) -> WorkflowNodeRun:
    run = await run_repo.get_run(workspace_id=workspace_id, run_id=run_id)
    if run is None or run.workflow_id != workflow_id:
        raise WorkflowNotRunnableError(workflow_id)

    node_run = await run_repo.get_node_run(workflow_run_id=run_id, node_id=node_id)
    if node_run is None or node_run.status.value != "paused_for_approval":
        raise NodeNotPausedError(node_id)

    resolved = await run_repo.resolve_approval(
        node_run_id=node_run.id, decision=decision, approved_by_user_id=approved_by_user_id
    )

    if decision == "rejected":
        await run_repo.update_run_status(
            run_id=run_id, status="error", error_message=f"node {node_id} rejected"
        )
        return resolved

    version = await workflow_repo.get_version(
        workflow_id=workflow_id, version_id=run.workflow_version_id
    )
    outgoing = version.outgoing_edges(node_id) if version is not None else []
    if not outgoing:
        # Approval was the last step on this branch — same "any other
        # branch still active?" check the worker's own `_advance` makes.
        remaining = await run_repo.list_node_runs(workflow_run_id=run_id)
        still_active = any(
            nr.status.value in ("queued", "running", "paused_for_approval") for nr in remaining
        )
        if not still_active:
            await run_repo.update_run_status(run_id=run_id, status="success")
    else:
        await run_repo.update_run_status(run_id=run_id, status="running")
        for edge in outgoing:
            await producer.enqueue(
                job_type="workflow_node",
                payload={"workflow_run_id": run_id, "node_id": edge.to_node_id},
            )

    return resolved
