"""`/api/v1/workspaces/{workspace_id}/workflows/{workflow_id}/runs` —
run submission, status, per-node status, and approval resolution
(CLAUDE.md §7 REST conventions). Authoring lives in `workflows.py` —
this router is execution only, mirroring `agents.py`'s split between
agent CRUD and run submission.

No SSE stream for workflow runs (docs/adr/0016, a deliberate scope
line): DAG nodes complete on the order of seconds-to-minutes, not
token-by-token, so per-node polling already satisfies the acceptance
criteria without a second streaming mechanism alongside Phase 4/9's.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_member,
    require_viewer,
)
from agentverse_api.billing_service.application.quota_service import (
    QuotaExceededError,
    QuotaService,
)
from agentverse_api.billing_service.domain.plan import MeteredDimension
from agentverse_api.billing_service.interface.dependencies.services import get_quota_service
from agentverse_api.orchestration_service.application.execute_workflow import (
    LockFactory,
    execute_workflow,
)
from agentverse_api.orchestration_service.application.resolve_workflow_approval import (
    NodeNotPausedError,
    resolve_workflow_approval,
)
from agentverse_api.orchestration_service.domain.ports.workflow_repository import (
    WorkflowRepository,
)
from agentverse_api.orchestration_service.domain.ports.workflow_run_repository import (
    WorkflowRunRepository,
)
from agentverse_api.orchestration_service.domain.run_exceptions import RunSubmissionConflictError
from agentverse_api.orchestration_service.domain.workflow_entities import (
    WorkflowNodeRun,
    WorkflowRun,
)
from agentverse_api.orchestration_service.domain.workflow_exceptions import (
    WorkflowNotRunnableError,
)
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_job_queue_producer,
    get_lock_factory,
    get_workflow_repository,
    get_workflow_run_repository,
)
from agentverse_api.orchestration_service.interface.schemas.workflows import (
    ResolveApprovalRequest,
    TriggerWorkflowRequest,
    WorkflowNodeRunResponse,
    WorkflowRunResponse,
)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/workflows/{workflow_id}/runs", tags=["workflows"]
)


def _run_response(run: WorkflowRun) -> WorkflowRunResponse:
    return WorkflowRunResponse(
        id=run.id,
        workflow_id=run.workflow_id,
        status=run.status.value,
        idempotency_key=run.idempotency_key,
        cost_micro_usd=run.cost_micro_usd,
        error_message=run.error_message,
        created_at=run.created_at,
    )


def _node_run_response(node_run: WorkflowNodeRun) -> WorkflowNodeRunResponse:
    return WorkflowNodeRunResponse(
        id=node_run.id,
        node_id=node_run.node_id,
        status=node_run.status.value,
        output=node_run.output,
        agent_run_id=node_run.agent_run_id,
        team_session_id=node_run.team_session_id,
        approval_decision=node_run.approval_decision,
        sequence=node_run.sequence,
        started_at=node_run.started_at,
        completed_at=node_run.completed_at,
    )


@router.post("", response_model=WorkflowRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_workflow_route(
    workflow_id: str,
    body: TriggerWorkflowRequest,
    context: WorkspaceContext = Depends(require_member),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
    run_repo: WorkflowRunRepository = Depends(get_workflow_run_repository),
    producer: JobQueueProducer = Depends(get_job_queue_producer),
    lock_factory: LockFactory = Depends(get_lock_factory),
    quota: QuotaService = Depends(get_quota_service),
) -> WorkflowRunResponse:
    # Metered before anything is enqueued, same discipline as agent-run
    # submission — checking after the fact is too late, the cost is
    # already committed. Per-node sub-run cost is not separately gated
    # here (docs/adr/0016, a deliberate scope line): each node's own
    # agent_run/team_session row goes through the existing agent-run
    # cost/bounds machinery once it executes.
    try:
        await quota.enforce(
            workspace_id=context.workspace_id, dimension=MeteredDimension.WORKFLOW_EXECUTIONS
        )
    except QuotaExceededError as exc:
        decision = exc.decision
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "quota_exceeded",
                "message": str(exc),
                "dimension": decision.dimension.value,
                "allowance": decision.allowance,
                "used": decision.used,
                "resets_at": decision.resets_at.isoformat(),
            },
            headers={"Retry-After": str(decision.retry_after_seconds(datetime.now(UTC)))},
        ) from exc

    try:
        run = await execute_workflow(
            workspace_id=context.workspace_id,
            workflow_id=workflow_id,
            input=body.input,
            idempotency_key=idempotency_key,
            workflow_repo=workflow_repo,
            run_repo=run_repo,
            producer=producer,
            lock_factory=lock_factory,
        )
    except WorkflowNotRunnableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workflow has no published version with a start node",
        ) from exc
    except RunSubmissionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not confirm run submission — retry with the same Idempotency-Key",
        ) from exc

    return _run_response(run)


@router.get("/{run_id}", response_model=WorkflowRunResponse)
async def get_workflow_run_route(
    workflow_id: str,
    run_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    run_repo: WorkflowRunRepository = Depends(get_workflow_run_repository),
) -> WorkflowRunResponse:
    run = await run_repo.get_run(workspace_id=context.workspace_id, run_id=run_id)
    if run is None or run.workflow_id != workflow_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return _run_response(run)


@router.get("/{run_id}/nodes", response_model=list[WorkflowNodeRunResponse])
async def list_workflow_run_nodes_route(
    workflow_id: str,
    run_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    run_repo: WorkflowRunRepository = Depends(get_workflow_run_repository),
) -> list[WorkflowNodeRunResponse]:
    run = await run_repo.get_run(workspace_id=context.workspace_id, run_id=run_id)
    if run is None or run.workflow_id != workflow_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    node_runs = await run_repo.list_node_runs(workflow_run_id=run_id)
    return [_node_run_response(nr) for nr in node_runs]


@router.post("/{run_id}/nodes/{node_id}/resolve", response_model=WorkflowNodeRunResponse)
async def resolve_approval_route(
    workflow_id: str,
    run_id: str,
    node_id: str,
    body: ResolveApprovalRequest,
    context: WorkspaceContext = Depends(require_member),
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
    run_repo: WorkflowRunRepository = Depends(get_workflow_run_repository),
    producer: JobQueueProducer = Depends(get_job_queue_producer),
) -> WorkflowNodeRunResponse:
    try:
        node_run = await resolve_workflow_approval(
            workspace_id=context.workspace_id,
            workflow_id=workflow_id,
            run_id=run_id,
            node_id=node_id,
            decision=body.decision,  # type: ignore[arg-type]  # validated by ResolveApprovalRequest's pattern
            approved_by_user_id=context.user_id,
            workflow_repo=workflow_repo,
            run_repo=run_repo,
            producer=producer,
        )
    except WorkflowNotRunnableError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found") from exc
    except NodeNotPausedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return _node_run_response(node_run)
