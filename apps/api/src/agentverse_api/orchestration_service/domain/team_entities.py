"""Multi-agent team domain entities — plain dataclasses, zero
framework/ORM imports (CLAUDE.md §5).

A **team** is a stored, versioned composition of existing agents plus a
topology. It is deliberately built *over* Phase 4's `agents` /
`agent_versions` rather than beside them: a team member is a pointer to a
published agent, so everything an agent already has (instructions, model,
tools, knowledge bases, guardrails) applies unchanged when it runs inside
a team. There is no second agent definition to keep in sync.

Naming note: "team" here means a team of *agents*. Workspace membership
(humans and RBAC roles) lives in `workspace_members` and is a different
concept entirely — the two never share a table, a route, or a repository.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class TeamTopology(StrEnum):
    """The supported orchestration shapes.

    Deliberately a closed set (`ai-architect`: topology follows the task,
    and the simplest sufficient one is the default). Each maps to a
    concrete OpenAI Agents SDK construction — see
    `apps/worker/agentverse_worker/teams/topologies.py` — never to a
    hand-rolled control loop.
    """

    #: One supervisor holds SDK `handoff()` targets for every worker and
    #: decides at run time who to delegate to. The SDK owns the
    #: delegation; AgentVerse owns which agents are reachable.
    SUPERVISOR_WORKER = "supervisor_worker"

    #: Planner drafts, executor performs, critic reviews. Use when
    #: verification quality matters more than latency — it roughly
    #: triples cost, so it is never the default.
    PLANNER_EXECUTOR_CRITIC = "planner_executor_critic"

    #: Members run in configured order, each receiving the previous
    #: member's typed handoff payload.
    SEQUENTIAL = "sequential"

    #: Members run concurrently on the same input; a designated
    #: aggregator (or the supervisor) merges their results.
    PARALLEL = "parallel"


class TeamMemberRole(StrEnum):
    """What a member does inside the topology.

    Role is a *team-level* assignment, not a property of the agent: the
    same agent can be a worker in one team and the critic in another,
    without duplicating its definition.
    """

    SUPERVISOR = "supervisor"
    PLANNER = "planner"
    EXECUTOR = "executor"
    CRITIC = "critic"
    RESEARCHER = "researcher"
    CODER = "coder"
    WRITER = "writer"
    WORKER = "worker"
    AGGREGATOR = "aggregator"


class MemoryScope(StrEnum):
    """Who can read a shared-memory entry.

    The sharing rule is stored per entry rather than inferred, so
    widening access is an explicit, auditable write rather than a
    side effect of some other change.
    """

    #: Readable by every member for the lifetime of the team.
    TEAM = "team"
    #: Readable by every member, but only within one session.
    SESSION = "session"
    #: Readable only by the agent that wrote it.
    AGENT = "agent"


class TeamSessionStatus(StrEnum):
    """Mirrors `RunStatus`'s vocabulary deliberately — a team session is
    a run, and a UI that already renders run status should not need a
    second, near-identical status enum.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


class HandoffKind(StrEnum):
    """How a handoff was decided.

    `AUTOMATIC` is the SDK deciding via its own `handoff()` tool call.
    The rest are AgentVerse's orchestration layer choosing, which is why
    they are recorded distinctly — "the model chose this" and "the
    topology dictated this" are different facts when debugging a run.
    """

    AUTOMATIC = "automatic"
    MANUAL = "manual"
    CONDITIONAL = "conditional"
    PARALLEL = "parallel"


class CommunicationKind(StrEnum):
    """The structured message vocabulary agents exchange.

    Agents never exchange free text between themselves — every
    inter-agent message is one of these, carrying a typed payload
    (CLAUDE.md §4: an agent never silently mutates another's context).
    """

    TASK_REQUEST = "task_request"
    TASK_RESULT = "task_result"
    CONTEXT_SHARE = "context_share"
    INTERMEDIATE_RESULT = "intermediate_result"
    ERROR_REPORT = "error_report"


@dataclass(frozen=True, slots=True)
class TeamMember:
    id: str
    team_id: str
    workspace_id: str
    #: Points at an `agents.id`. The agent's own published version supplies
    #: instructions/model/tools — a team never redefines them.
    agent_id: str
    role: TeamMemberRole
    #: Drag-and-drop order in the builder; also the execution order for
    #: SEQUENTIAL topologies.
    position: int
    #: Overrides the agent's own description for the supervisor's
    #: delegation decision. Tool/agent descriptions are part of the
    #: prompt (`mcp-expert`), so a vague one degrades routing as much as
    #: a bad system prompt.
    handoff_description: str | None
    #: When false, this member is reachable only by explicit/manual
    #: handoff, never by the supervisor's own choice.
    can_receive_handoff: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Team:
    id: str
    workspace_id: str
    name: str
    description: str | None
    topology: TeamTopology
    #: Prepended to the supervisor's instructions. The per-agent
    #: instructions still apply; this is the team's shared brief.
    objective: str | None
    #: Bounds, stored per team rather than global, because a research
    #: team and a triage team have legitimately different ceilings.
    #: All three are required (Rule 17 — steps alone is not enough).
    max_turns: int
    max_cost_micro_usd: int
    timeout_seconds: int
    #: Whether members can read each other's `shared_memory` entries.
    shared_memory_enabled: bool
    #: Knowledge bases every member retrieves from, on top of whatever
    #: each agent has attached individually.
    shared_knowledge_base_ids: list[str] = field(default_factory=list)
    created_by_user_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.min)
    updated_at: datetime = field(default_factory=lambda: datetime.min)
    members: list[TeamMember] = field(default_factory=list)

    def supervisor(self) -> TeamMember | None:
        return next((m for m in self.members if m.role is TeamMemberRole.SUPERVISOR), None)

    def ordered_members(self) -> list[TeamMember]:
        return sorted(self.members, key=lambda m: (m.position, m.id))


@dataclass(frozen=True, slots=True)
class TeamSession:
    """One execution of a team. The multi-agent analogue of `AgentRun`,
    kept as its own table rather than overloading `agent_runs`: a team
    session has no single `agent_version_id`, and forcing one would mean
    lying about which configuration produced the result.
    """

    id: str
    workspace_id: str
    team_id: str
    status: TeamSessionStatus
    input: dict[str, object]
    output: str | None
    error_message: str | None
    cost_micro_usd: int | None
    total_turns: int
    idempotency_key: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class HandoffRecord:
    id: str
    workspace_id: str
    session_id: str
    from_agent_id: str | None
    to_agent_id: str
    kind: HandoffKind
    #: The typed `HandoffContract` payload, never a raw transcript.
    contract: dict[str, object]
    reason: str | None
    sequence: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SharedMemoryEntry:
    id: str
    workspace_id: str
    team_id: str
    #: Null for `TEAM`-scoped entries, which outlive any one session.
    session_id: str | None
    agent_id: str | None
    scope: MemoryScope
    key: str
    value: dict[str, object]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CommunicationLogEntry:
    id: str
    workspace_id: str
    session_id: str
    from_agent_id: str | None
    to_agent_id: str | None
    kind: CommunicationKind
    content: dict[str, object]
    sequence: int
    created_at: datetime
