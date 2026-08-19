"""Workflow domain entities — plain dataclasses, zero framework/ORM
imports (CLAUDE.md §5). A `Workflow` is stored, versioned configuration,
mirroring the `Agent`/`AgentVersion` split (Phase 4): `Workflow` is
identity/lifecycle metadata, `WorkflowVersion` is the immutable DAG
snapshot the builder writes and the engine reads.

Node/edge `id`s are caller-supplied (the canvas assigns them when a node
is added), not server-generated — an edge must be able to reference a
node before the version it belongs to exists as a row (docs/adr/0016).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class WorkflowStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class WorkflowNodeType(StrEnum):
    """The supported node vocabulary — deliberately closed (`ai-architect`:
    topology follows the task). `AGENT_STEP`/`TEAM_STEP` are the only
    types that execute anything, and both delegate to Phase 9's stable
    entrypoints (`run_agent`/`execute_team`) — never a reimplementation.
    """

    AGENT_STEP = "agent_step"
    TEAM_STEP = "team_step"
    CONDITIONAL_BRANCH = "conditional_branch"
    HUMAN_APPROVAL = "human_approval"
    PARALLEL_FANOUT = "parallel_fanout"


#: Node types that delegate to Phase 9 and therefore carry exactly one of
#: `agent_id`/`team_id`. Every other type carries neither — enforced both
#: by a DB CHECK constraint and by `workflow_graph.validate_workflow_graph`.
EXECUTABLE_NODE_TYPES = frozenset({WorkflowNodeType.AGENT_STEP, WorkflowNodeType.TEAM_STEP})


class WorkflowRunStatus(StrEnum):
    """Mirrors `RunStatus`/`TeamSessionStatus`'s vocabulary deliberately,
    plus `PAUSED` — the durable human-approval wait state, which neither
    of those needed. A UI that already renders run status should not
    need a third, near-identical status enum.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class WorkflowNodeRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    #: Durable pause: this state is a Postgres row, not anything held in
    #: worker memory, so it survives a worker restart by construction.
    PAUSED_FOR_APPROVAL = "paused_for_approval"


_TERMINAL_NODE_RUN_STATUSES = frozenset(
    {
        WorkflowNodeRunStatus.SUCCESS,
        WorkflowNodeRunStatus.ERROR,
        WorkflowNodeRunStatus.CANCELLED,
        WorkflowNodeRunStatus.SKIPPED,
    }
)


@dataclass(frozen=True, slots=True)
class WorkflowNode:
    id: str
    type: WorkflowNodeType
    position_x: float
    position_y: float
    #: Node-type-specific: `input_template` for agent_step/team_step,
    #: `message` for human_approval. Empty for conditional_branch (its
    #: conditions live on outgoing edges) and parallel_fanout.
    config: dict[str, Any]
    agent_id: str | None = None
    team_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkflowEdge:
    id: str
    from_node_id: str
    to_node_id: str
    #: `{"field", "operator", "value"}` — a simple comparison, no
    #: expression language. `None` is the default/else edge, taken when
    #: no sibling edge's condition matches (or the only edge out of a
    #: non-branching node).
    condition: dict[str, Any] | None = None
    #: Evaluation order among a `conditional_branch` node's outgoing
    #: edges; irrelevant otherwise.
    branch_order: int | None = None


@dataclass(frozen=True, slots=True)
class WorkflowVersion:
    id: str
    workflow_id: str
    version_number: int
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
    created_by_user_id: str
    created_at: datetime

    def start_nodes(self) -> list[WorkflowNode]:
        """Nodes with no incoming edge — where a run begins."""
        targets = {edge.to_node_id for edge in self.edges}
        return [node for node in self.nodes if node.id not in targets]

    def outgoing_edges(self, node_id: str) -> list[WorkflowEdge]:
        return sorted(
            (e for e in self.edges if e.from_node_id == node_id),
            key=lambda e: (e.branch_order is None, e.branch_order or 0),
        )

    def node_by_id(self, node_id: str) -> WorkflowNode | None:
        return next((n for n in self.nodes if n.id == node_id), None)


@dataclass(frozen=True, slots=True)
class Workflow:
    id: str
    workspace_id: str
    name: str
    description: str | None
    status: WorkflowStatus
    published_version_id: str | None
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    id: str
    workspace_id: str
    workflow_id: str
    workflow_version_id: str
    status: WorkflowRunStatus
    input: dict[str, Any]
    idempotency_key: str | None
    cost_micro_usd: int | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class WorkflowNodeRun:
    id: str
    workflow_run_id: str
    node_id: str
    agent_run_id: str | None
    team_session_id: str | None
    status: WorkflowNodeRunStatus
    output: dict[str, Any] | None
    approval_decision: str | None
    approved_by_user_id: str | None
    approved_at: datetime | None
    sequence: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_NODE_RUN_STATUSES


@dataclass(frozen=True, slots=True)
class WorkflowVersionDiff:
    """Computed at request time from two `WorkflowVersion`s — no new
    storage (`diff_workflow_versions.py`).
    """

    added_nodes: list[WorkflowNode] = field(default_factory=list)
    removed_nodes: list[WorkflowNode] = field(default_factory=list)
    changed_nodes: list[tuple[WorkflowNode, WorkflowNode]] = field(default_factory=list)
    added_edges: list[WorkflowEdge] = field(default_factory=list)
    removed_edges: list[WorkflowEdge] = field(default_factory=list)
