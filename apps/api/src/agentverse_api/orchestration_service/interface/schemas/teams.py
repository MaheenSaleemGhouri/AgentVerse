"""Request/response models for the team API.

Every free-text field that can reach an LLM prompt is capped, matching
the agent schemas: `objective` is prepended to every member's
instructions, so an unbounded one is a cost multiplier across the whole
team as well as a prompt-injection surface (CLAUDE.md §7).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

TopologyLiteral = Literal["supervisor_worker", "planner_executor_critic", "sequential", "parallel"]
RoleLiteral = Literal[
    "supervisor",
    "planner",
    "executor",
    "critic",
    "researcher",
    "coder",
    "writer",
    "worker",
    "aggregator",
]
SessionStatusLiteral = Literal["queued", "running", "success", "error", "cancelled"]
HandoffKindLiteral = Literal["automatic", "manual", "conditional", "parallel"]
CommunicationKindLiteral = Literal[
    "task_request", "task_result", "context_share", "intermediate_result", "error_report"
]

#: Defaults for a new team's bounds. Chosen to be generous enough for a
#: real multi-stage run and tight enough that a misconfigured team fails
#: fast rather than expensively — all three are editable per team.
DEFAULT_MAX_TURNS = 20
DEFAULT_MAX_COST_MICRO_USD = 1_000_000  # $1.00
DEFAULT_TIMEOUT_SECONDS = 300


class CreateTeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    topology: TopologyLiteral
    # Prepended to every member's instructions — capped for the same
    # reason as an agent's own system_instructions, times team size.
    objective: str | None = Field(default=None, max_length=4000)
    max_turns: int = Field(default=DEFAULT_MAX_TURNS, ge=1, le=200)
    max_cost_micro_usd: int = Field(default=DEFAULT_MAX_COST_MICRO_USD, ge=1, le=100_000_000)
    timeout_seconds: int = Field(default=DEFAULT_TIMEOUT_SECONDS, ge=5, le=3600)
    shared_memory_enabled: bool = True
    shared_knowledge_base_ids: list[str] = Field(default_factory=list, max_length=10)


class UpdateTeamRequest(BaseModel):
    """Every field optional — an omitted field is left unchanged.

    `None` is a legitimate value for `description` and `objective`
    (clearing them), so "omitted" and "set to null" are distinguished by
    presence in the request body, not by the value being null.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    topology: TopologyLiteral | None = None
    objective: str | None = Field(default=None, max_length=4000)
    max_turns: int | None = Field(default=None, ge=1, le=200)
    max_cost_micro_usd: int | None = Field(default=None, ge=1, le=100_000_000)
    timeout_seconds: int | None = Field(default=None, ge=5, le=3600)
    shared_memory_enabled: bool | None = None
    shared_knowledge_base_ids: list[str] | None = Field(default=None, max_length=10)


class AddMemberRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=64)
    role: RoleLiteral
    position: int = Field(default=0, ge=0, le=100)
    # Read by the delegating model to choose this member. A tool/agent
    # description is part of the prompt, so a vague one degrades routing
    # as much as a vague system prompt.
    handoff_description: str | None = Field(default=None, max_length=500)
    can_receive_handoff: bool = True


class ReorderMembersRequest(BaseModel):
    """Drag-and-drop ordering, applied as one write.

    The full ordered list, not a delta: a delta would need the client and
    server to agree on a starting state, and for a `sequential` team a
    disagreement changes execution order rather than just the display.
    """

    member_ids: list[str] = Field(min_length=1, max_length=50)


class ExecuteTeamRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=16000)


class TeamMemberResponse(BaseModel):
    id: str
    team_id: str
    agent_id: str
    # The literal union, not `str`: it flows into the generated TS
    # contract, where the frontend's role/topology lookup tables are
    # exhaustive over it. Declaring `str` here would push a redundant
    # runtime fallback into every call site on the client.
    role: RoleLiteral
    position: int
    handoff_description: str | None
    can_receive_handoff: bool
    created_at: datetime


class TeamResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str | None
    topology: TopologyLiteral
    objective: str | None
    max_turns: int
    max_cost_micro_usd: int
    timeout_seconds: int
    shared_memory_enabled: bool
    shared_knowledge_base_ids: list[str]
    created_at: datetime
    updated_at: datetime
    members: list[TeamMemberResponse]


class TeamSessionResponse(BaseModel):
    id: str
    workspace_id: str
    team_id: str
    status: SessionStatusLiteral
    input: dict[str, Any]
    output: str | None
    error_message: str | None
    #: Integer micro-USD, never a float (Rule 15).
    cost_micro_usd: int | None
    total_turns: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class TeamSessionPage(BaseModel):
    """Cursor-paginated, matching the shape every other append-mostly
    collection uses (CLAUDE.md §7).
    """

    data: list[TeamSessionResponse]
    next_cursor: str | None
    has_more: bool


class ExecutionEventResponse(BaseModel):
    id: str
    type: str
    sequence: int
    agent_id: str | None
    payload: dict[str, Any]
    cost_micro_usd: int | None
    created_at: datetime


class HandoffResponse(BaseModel):
    id: str
    session_id: str
    from_agent_id: str | None
    to_agent_id: str
    kind: HandoffKindLiteral
    #: The typed `HandoffContract`, as stored — summary and pointers,
    #: never a transcript.
    contract: dict[str, Any]
    reason: str | None
    sequence: int
    created_at: datetime


class CommunicationResponse(BaseModel):
    id: str
    session_id: str
    from_agent_id: str | None
    to_agent_id: str | None
    kind: CommunicationKindLiteral
    content: dict[str, Any]
    sequence: int
    created_at: datetime


class TeamAnalyticsResponse(BaseModel):
    total_sessions: int
    succeeded_sessions: int
    failed_sessions: int
    total_cost_micro_usd: int
    average_cost_micro_usd: int
    total_turns: int
    total_handoffs: int
