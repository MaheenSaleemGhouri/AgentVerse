from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from agentverse_api.orchestration_service.domain.workflow_entities import WorkflowNodeType

#: Node/edge ids are client-generated (the canvas assigns them) — loosely
#: validated as opaque strings up to a bound length rather than a strict
#: UUID pattern, since the id space is not required to be a UUID, only
#: unique within the submitted graph (CLAUDE.md §7: opaque string IDs).
_NodeId = Field(min_length=1, max_length=64)


class CreateWorkflowRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class WorkflowResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str | None
    status: str
    published_version_id: str | None
    created_at: datetime
    updated_at: datetime


class WorkflowNodeSchema(BaseModel):
    id: str = _NodeId
    type: WorkflowNodeType
    position_x: float = 0
    position_y: float = 0
    config: dict[str, Any] = Field(default_factory=dict)
    agent_id: str | None = None
    team_id: str | None = None


class WorkflowEdgeSchema(BaseModel):
    id: str = _NodeId
    from_node_id: str = _NodeId
    to_node_id: str = _NodeId
    condition: dict[str, Any] | None = None
    branch_order: int | None = None


class CreateWorkflowVersionRequest(BaseModel):
    #: Capped: a workflow this large is almost certainly a modeling
    #: mistake, and an unbounded graph is an unbounded validation/DAG-
    #: traversal cost per save.
    nodes: list[WorkflowNodeSchema] = Field(default_factory=list, max_length=200)
    edges: list[WorkflowEdgeSchema] = Field(default_factory=list, max_length=400)


class WorkflowVersionResponse(BaseModel):
    id: str
    workflow_id: str
    version_number: int
    nodes: list[WorkflowNodeSchema]
    edges: list[WorkflowEdgeSchema]
    created_at: datetime


class CreateWorkflowResponse(BaseModel):
    workflow: WorkflowResponse
    version: WorkflowVersionResponse


class PublishWorkflowRequest(BaseModel):
    version_id: str


class WorkflowVersionDiffResponse(BaseModel):
    added_nodes: list[WorkflowNodeSchema]
    removed_nodes: list[WorkflowNodeSchema]
    changed_nodes: list[tuple[WorkflowNodeSchema, WorkflowNodeSchema]]
    added_edges: list[WorkflowEdgeSchema]
    removed_edges: list[WorkflowEdgeSchema]


class TriggerWorkflowRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunResponse(BaseModel):
    id: str
    workflow_id: str
    status: str
    idempotency_key: str | None
    cost_micro_usd: int | None
    error_message: str | None
    created_at: datetime


class WorkflowNodeRunResponse(BaseModel):
    id: str
    node_id: str
    status: str
    output: dict[str, Any] | None
    agent_run_id: str | None
    team_session_id: str | None
    approval_decision: str | None
    sequence: int
    started_at: datetime | None
    completed_at: datetime | None


class ResolveApprovalRequest(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = Field(default=None, max_length=2000)
