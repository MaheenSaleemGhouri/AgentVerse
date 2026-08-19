"""`/api/v1/workspaces/{workspace_id}/workflows` — workflow CRUD,
versioning, diff, and publish (CLAUDE.md §7 REST conventions). Run
submission/status lives in `workflow_runs.py` — this router is authoring
only, mirroring `agents.py`'s split between agent CRUD and run
submission.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_member,
    require_viewer,
)
from agentverse_api.orchestration_service.application.create_workflow import create_workflow
from agentverse_api.orchestration_service.application.create_workflow_version import (
    create_workflow_version,
)
from agentverse_api.orchestration_service.application.diff_workflow_versions import (
    diff_workflow_versions,
)
from agentverse_api.orchestration_service.domain.ports.workflow_repository import (
    WorkflowRepository,
)
from agentverse_api.orchestration_service.domain.workflow_entities import (
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowVersion,
)
from agentverse_api.orchestration_service.domain.workflow_exceptions import (
    InvalidWorkflowGraphError,
)
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_workflow_repository,
)
from agentverse_api.orchestration_service.interface.schemas.workflows import (
    CreateWorkflowRequest,
    CreateWorkflowResponse,
    CreateWorkflowVersionRequest,
    PublishWorkflowRequest,
    WorkflowEdgeSchema,
    WorkflowNodeSchema,
    WorkflowResponse,
    WorkflowVersionDiffResponse,
    WorkflowVersionResponse,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/workflows", tags=["workflows"])


def _workflow_response(workflow: Workflow) -> WorkflowResponse:
    return WorkflowResponse(
        id=workflow.id,
        workspace_id=workflow.workspace_id,
        name=workflow.name,
        description=workflow.description,
        status=workflow.status.value,
        published_version_id=workflow.published_version_id,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
    )


def _version_response(version: WorkflowVersion) -> WorkflowVersionResponse:
    return WorkflowVersionResponse(
        id=version.id,
        workflow_id=version.workflow_id,
        version_number=version.version_number,
        nodes=[_node_schema(n) for n in version.nodes],
        edges=[_edge_schema(e) for e in version.edges],
        created_at=version.created_at,
    )


def _node_schema(node: WorkflowNode) -> WorkflowNodeSchema:
    return WorkflowNodeSchema(
        id=node.id,
        type=node.type,
        position_x=node.position_x,
        position_y=node.position_y,
        config=node.config,
        agent_id=node.agent_id,
        team_id=node.team_id,
    )


def _edge_schema(edge: WorkflowEdge) -> WorkflowEdgeSchema:
    return WorkflowEdgeSchema(
        id=edge.id,
        from_node_id=edge.from_node_id,
        to_node_id=edge.to_node_id,
        condition=edge.condition,
        branch_order=edge.branch_order,
    )


async def _get_workflow_or_404(
    workflow_id: str, context: WorkspaceContext, workflow_repo: WorkflowRepository
) -> Workflow:
    workflow = await workflow_repo.get_workflow(
        workspace_id=context.workspace_id, workflow_id=workflow_id
    )
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return workflow


@router.post("", response_model=CreateWorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow_route(
    body: CreateWorkflowRequest,
    context: WorkspaceContext = Depends(require_member),
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
) -> CreateWorkflowResponse:
    workflow, version = await create_workflow(
        workspace_id=context.workspace_id,
        name=body.name,
        description=body.description,
        created_by_user_id=context.user_id,
        workflow_repo=workflow_repo,
    )
    return CreateWorkflowResponse(
        workflow=_workflow_response(workflow), version=_version_response(version)
    )


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows_route(
    context: WorkspaceContext = Depends(require_viewer),
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
) -> list[WorkflowResponse]:
    workflows = await workflow_repo.list_workflows(workspace_id=context.workspace_id)
    return [_workflow_response(w) for w in workflows]


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow_route(
    workflow_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
) -> WorkflowResponse:
    workflow = await _get_workflow_or_404(workflow_id, context, workflow_repo)
    return _workflow_response(workflow)


@router.get("/{workflow_id}/versions/latest", response_model=WorkflowVersionResponse)
async def get_latest_version_route(
    workflow_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
) -> WorkflowVersionResponse:
    await _get_workflow_or_404(workflow_id, context, workflow_repo)
    latest = await workflow_repo.get_latest_version(workflow_id=workflow_id)
    if latest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow has no version")
    return _version_response(latest)


@router.get("/{workflow_id}/versions/{version_id}", response_model=WorkflowVersionResponse)
async def get_version_route(
    workflow_id: str,
    version_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
) -> WorkflowVersionResponse:
    await _get_workflow_or_404(workflow_id, context, workflow_repo)
    version = await workflow_repo.get_version(workflow_id=workflow_id, version_id=version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    return _version_response(version)


@router.post(
    "/{workflow_id}/versions",
    response_model=WorkflowVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_version_route(
    workflow_id: str,
    body: CreateWorkflowVersionRequest,
    context: WorkspaceContext = Depends(require_member),
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
) -> WorkflowVersionResponse:
    await _get_workflow_or_404(workflow_id, context, workflow_repo)
    nodes = [
        WorkflowNode(
            id=n.id,
            type=n.type,
            position_x=n.position_x,
            position_y=n.position_y,
            config=n.config,
            agent_id=n.agent_id,
            team_id=n.team_id,
        )
        for n in body.nodes
    ]
    edges = [
        WorkflowEdge(
            id=e.id,
            from_node_id=e.from_node_id,
            to_node_id=e.to_node_id,
            condition=e.condition,
            branch_order=e.branch_order,
        )
        for e in body.edges
    ]
    try:
        version = await create_workflow_version(
            workflow_id=workflow_id,
            nodes=nodes,
            edges=edges,
            created_by_user_id=context.user_id,
            workflow_repo=workflow_repo,
        )
    except InvalidWorkflowGraphError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _version_response(version)


@router.get("/{workflow_id}/versions/{version_id}/diff", response_model=WorkflowVersionDiffResponse)
async def diff_versions_route(
    workflow_id: str,
    version_id: str,
    against: str = Query(..., description="The other version_id to diff against (the base)"),
    context: WorkspaceContext = Depends(require_viewer),
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
) -> WorkflowVersionDiffResponse:
    await _get_workflow_or_404(workflow_id, context, workflow_repo)
    to_version = await workflow_repo.get_version(workflow_id=workflow_id, version_id=version_id)
    from_version = await workflow_repo.get_version(workflow_id=workflow_id, version_id=against)
    if to_version is None or from_version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    diff = diff_workflow_versions(from_version, to_version)
    return WorkflowVersionDiffResponse(
        added_nodes=[_node_schema(n) for n in diff.added_nodes],
        removed_nodes=[_node_schema(n) for n in diff.removed_nodes],
        changed_nodes=[(_node_schema(b), _node_schema(a)) for b, a in diff.changed_nodes],
        added_edges=[_edge_schema(e) for e in diff.added_edges],
        removed_edges=[_edge_schema(e) for e in diff.removed_edges],
    )


@router.post("/{workflow_id}/publish", response_model=WorkflowResponse)
async def publish_workflow_route(
    workflow_id: str,
    body: PublishWorkflowRequest,
    context: WorkspaceContext = Depends(require_member),
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
) -> WorkflowResponse:
    await _get_workflow_or_404(workflow_id, context, workflow_repo)
    version = await workflow_repo.get_version(workflow_id=workflow_id, version_id=body.version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    published = await workflow_repo.publish_version(
        workflow_id=workflow_id, version_id=body.version_id
    )
    return _workflow_response(published)
