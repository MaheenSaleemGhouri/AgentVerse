"""SQLAlchemy ORM models for the agent-builder/runtime bounded context
(Phase 4). `agent_run_steps` is partitioned by `created_at` from this,
its first migration (`CLAUDE.md` §5 Scalability names this table
explicitly) — Postgres requires the partition key in every primary key
on a partitioned table, hence the composite `(id, created_at)` PK
instead of `id` alone.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from agentverse_api.infrastructure.orm_base import Base
from agentverse_api.orchestration_service.domain.agent_entities import AgentStatus
from agentverse_api.orchestration_service.domain.integration_entities import (
    AuthScheme,
    HealthStatus,
    InstallStatus,
    McpAvailability,
    McpTransport,
    PermissionLevel,
    ToolCallStatus,
)
from agentverse_api.orchestration_service.domain.knowledge_entities import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_DIMENSIONS,
    DocumentStatus,
)
from agentverse_api.orchestration_service.domain.run_entities import RunStatus, RunStepType
from agentverse_api.orchestration_service.domain.team_entities import (
    CommunicationKind,
    HandoffKind,
    MemoryScope,
    TeamMemberRole,
    TeamSessionStatus,
    TeamTopology,
)


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))


class AgentModel(Base):
    __tablename__ = "agents"

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[AgentStatus] = mapped_column(
        SqlEnum(AgentStatus, name="agent_status", values_callable=lambda e: [m.value for m in e]),
        default=AgentStatus.DRAFT,
    )
    # No FK to agent_versions here: that table's own FK back to `agents`
    # must exist first. The constraint is added by the migration via a
    # post-creation ALTER TABLE, not expressed on this ORM column.
    published_version_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), nullable=True, default=None
    )
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)


class AgentVersionModel(Base):
    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("agent_id", "version_number", name="uq_agent_version"),)

    id: Mapped[str] = _uuid_pk()
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime]


class AgentRunModel(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    agent_version_id: Mapped[str] = mapped_column(
        ForeignKey("agent_versions.id", ondelete="RESTRICT")
    )
    status: Mapped[RunStatus] = mapped_column(
        SqlEnum(RunStatus, name="run_status", values_callable=lambda e: [m.value for m in e]),
        default=RunStatus.QUEUED,
    )
    input: Mapped[dict[str, Any]] = mapped_column(JSONB)
    idempotency_key: Mapped[str | None] = mapped_column(Text, default=None)
    cost_micro_usd: Mapped[int | None] = mapped_column(BigInteger, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime]


class AgentRunStepModel(Base):
    """Partitioned by `created_at` (RANGE) — see the migration for the
    partition DDL, which `op.create_table` cannot express and is
    therefore raw SQL. The composite primary key is a Postgres
    requirement for partitioned tables (the partition key must be part
    of every unique/primary key), not a modeling choice.
    """

    __tablename__ = "agent_run_steps"
    __table_args__ = ({"postgresql_partition_by": "RANGE (created_at)"},)

    # Composite primary key (id, created_at) — Postgres requires the
    # partition key in every primary/unique key on a partitioned table,
    # so `id` cannot be a PK on its own here. Practically unique anyway
    # since `id` is a uuid4.
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    created_at: Mapped[datetime] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True)
    step_type: Mapped[RunStepType] = mapped_column(
        SqlEnum(RunStepType, name="run_step_type", values_callable=lambda e: [m.value for m in e])
    )
    sequence: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    cost_micro_usd: Mapped[int | None] = mapped_column(BigInteger, default=None)


# --- Knowledge bases (Phase 5) -----------------------------------------
# pgvector on the primary Postgres instance per ADR-0003 — the vector
# column is the semantic layer; `kb_chunks.content` alongside it is the
# durable source text (CLAUDE.md §8: the vector store is never the
# system of record).

_EMBEDDING_DIM = EMBEDDING_DIMENSIONS[DEFAULT_EMBEDDING_MODEL]


class KnowledgeBaseModel(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    # Recorded per knowledge base, not just per chunk: every chunk in one
    # KB must be embedded by the same model+version for its similarity
    # scores to mean anything, so the KB owns the authoritative pair and
    # ingestion reads it rather than each document choosing its own.
    embedding_model: Mapped[str] = mapped_column(Text)
    embedding_model_version: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)


class KbDocumentModel(Base):
    __tablename__ = "kb_documents"

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    content_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[DocumentStatus] = mapped_column(
        SqlEnum(
            DocumentStatus,
            name="kb_document_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=DocumentStatus.PENDING,
    )
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)


class KbChunkModel(Base):
    __tablename__ = "kb_chunks"
    __table_args__ = (
        # Idempotent ingestion (`vector-database-expert`): re-running
        # ingestion for an unchanged document must not duplicate chunks.
        # Enforced by the DB, not just by an application-level check,
        # because the ingestion job is retry-safe-by-redelivery.
        UniqueConstraint(
            "kb_document_id", "content_hash", "chunk_index", name="uq_kb_chunk_document_hash_index"
        ),
    )

    id: Mapped[str] = _uuid_pk()
    # Denormalized onto the chunk (not reached via kb_documents) so every
    # similarity query can pre-filter on workspace_id in the same
    # statement as the ANN search — CLAUDE.md §8 forbids post-filtering
    # an unscoped top-k, which both leaks tenant data and wrecks recall.
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    knowledge_base_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    kb_document_id: Mapped[str] = mapped_column(
        ForeignKey("kb_documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector(_EMBEDDING_DIM))
    embedding_model: Mapped[str] = mapped_column(Text)
    embedding_model_version: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime]


# --- Multi-agent teams (Phase 9) ---------------------------------------
# Built over Phase 4's `agents`/`agent_versions`, never beside them: a
# team member is a foreign key to an existing agent, so an agent's
# instructions, model, tools, and knowledge bases apply unchanged inside
# a team. There is deliberately no second agent definition to keep in
# sync (CLAUDE.md Rule 3).


class TeamModel(Base):
    __tablename__ = "teams"

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    topology: Mapped[TeamTopology] = mapped_column(
        SqlEnum(TeamTopology, name="team_topology", values_callable=lambda e: [m.value for m in e])
    )
    objective: Mapped[str | None] = mapped_column(Text, default=None)
    # All three bounds are columns, not config constants: Rule 17 requires
    # step, cost, AND time ceilings, and a research team legitimately
    # needs different ones from a triage team.
    max_turns: Mapped[int] = mapped_column(Integer, default=20)
    max_cost_micro_usd: Mapped[int] = mapped_column(BigInteger, default=1_000_000)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    shared_memory_enabled: Mapped[bool] = mapped_column(default=True)
    # jsonb rather than a join table: this is an unordered set of ids
    # validated by the application layer, with no attributes of its own
    # (CLAUDE.md §8 — the DB stores flexibility, the API enforces shape).
    shared_knowledge_base_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)


class TeamMemberModel(Base):
    """An agent's seat in a team.

    Named `team_members` per the phase spec. Note this is *agents* in a
    team, entirely distinct from `workspace_members` (humans + RBAC) —
    the two never share a table or a route.
    """

    __tablename__ = "team_members"
    __table_args__ = (
        # One seat per agent per team. Two seats would make handoff
        # targeting ambiguous and silently double a parallel fan-out.
        UniqueConstraint("team_id", "agent_id", name="uq_team_member_agent"),
    )

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    # RESTRICT, not CASCADE: deleting an agent that a team depends on
    # should fail loudly rather than silently leaving a team that can no
    # longer run the topology it claims to have.
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="RESTRICT"), index=True)
    role: Mapped[TeamMemberRole] = mapped_column(
        SqlEnum(
            TeamMemberRole, name="team_member_role", values_callable=lambda e: [m.value for m in e]
        )
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    handoff_description: Mapped[str | None] = mapped_column(Text, default=None)
    can_receive_handoff: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime]


class TeamSessionModel(Base):
    """One execution of a team — the multi-agent analogue of `agent_runs`.

    Kept as its own table rather than overloading `agent_runs`, which
    requires a single `agent_version_id`. A team session has no single
    version, and inventing one would misreport which configuration
    produced the result.
    """

    __tablename__ = "team_sessions"

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    status: Mapped[TeamSessionStatus] = mapped_column(
        SqlEnum(
            TeamSessionStatus,
            name="team_session_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=TeamSessionStatus.QUEUED,
    )
    input: Mapped[dict[str, Any]] = mapped_column(JSONB)
    output: Mapped[str | None] = mapped_column(Text, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    cost_micro_usd: Mapped[int | None] = mapped_column(BigInteger, default=None)
    total_turns: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime]


class HandoffModel(Base):
    """Every transfer of control between agents in a session.

    `contract` holds the typed `HandoffContract` payload — a summary plus
    pointers, never a raw transcript dump (CLAUDE.md §4). Recorded even
    for SDK-initiated automatic handoffs, so "who passed what to whom,
    and why" is answerable from the database alone.
    """

    __tablename__ = "handoffs"

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("team_sessions.id", ondelete="CASCADE"), index=True
    )
    # Null when the orchestrator itself dispatched the first agent —
    # there is no originating agent for the opening move.
    from_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), default=None
    )
    to_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"))
    kind: Mapped[HandoffKind] = mapped_column(
        SqlEnum(HandoffKind, name="handoff_kind", values_callable=lambda e: [m.value for m in e])
    )
    contract: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    sequence: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime]


class SharedMemoryModel(Base):
    """Team-scoped working memory.

    Deliberately relational, not vector-backed: this is structured state
    agents write and read by key ("the plan", "findings so far"), not
    something retrieved by semantic similarity. Phase 5's `kb_chunks` is
    the semantic store and stays completely separate — the roadmap names
    cross-contamination between "what an agent remembers" and "what a
    document says" as this phase's highest-risk mistake.
    """

    __tablename__ = "shared_memory"
    __table_args__ = (
        # Upsert target: writing the same key twice updates rather than
        # accumulating duplicates a reader would have to disambiguate.
        # NULLS NOT DISTINCT is load-bearing: `session_id`/`agent_id` are
        # null for team-scoped entries, and Postgres's default treats
        # every NULL as distinct — which would silently turn the upsert
        # into an append for exactly the widest-shared scope.
        UniqueConstraint(
            "team_id",
            "session_id",
            "agent_id",
            "key",
            name="uq_shared_memory_scope_key",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    # Null for TEAM-scoped entries, which outlive any one session.
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("team_sessions.id", ondelete="CASCADE"), default=None, index=True
    )
    agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), default=None
    )
    scope: Mapped[MemoryScope] = mapped_column(
        SqlEnum(MemoryScope, name="memory_scope", values_callable=lambda e: [m.value for m in e])
    )
    key: Mapped[str] = mapped_column(Text)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class CommunicationLogModel(Base):
    """Every structured message exchanged between agents.

    Distinct from `handoffs`: a handoff transfers *control*, a
    communication carries *content*. A supervisor can share context with
    a worker without handing control to it, and both facts need to be
    recoverable independently when explaining a run.
    """

    __tablename__ = "communication_logs"

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("team_sessions.id", ondelete="CASCADE"), index=True
    )
    from_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), default=None
    )
    to_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), default=None
    )
    kind: Mapped[CommunicationKind] = mapped_column(
        SqlEnum(
            CommunicationKind,
            name="communication_kind",
            values_callable=lambda e: [m.value for m in e],
        )
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    sequence: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime]


class ExecutionEventModel(Base):
    """The team-run trace stream — the multi-agent analogue of
    `agent_run_steps`, and partitioned by `created_at` for the same
    reason (CLAUDE.md §5 names high-volume trace tables explicitly).

    Composite `(id, created_at)` primary key is a Postgres requirement
    for partitioned tables, not a modeling choice.
    """

    __tablename__ = "execution_events"
    __table_args__ = ({"postgresql_partition_by": "RANGE (created_at)"},)

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    created_at: Mapped[datetime] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True)
    workspace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True)
    # Free-form rather than an enum: the event vocabulary grows with each
    # topology, and a new event type must never require a migration to
    # start being recorded. The frontend union is the enforcement point.
    event_type: Mapped[str] = mapped_column(Text)
    agent_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), default=None)
    sequence: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    cost_micro_usd: Mapped[int | None] = mapped_column(BigInteger, default=None)


class TeamSessionItemModel(Base):
    """Durable backing store for the Agents SDK `Session` protocol.

    The SDK ships in-memory and SQLite sessions; on a multi-instance
    worker fleet both silently lose conversation state when a follow-up
    turn lands on a different instance (CLAUDE.md §4). This table is what
    `PostgresTeamSession` reads and writes.

    `id` is a database identity rather than a UUID because it carries
    ordering as well as identity — `get_items` is chronological and
    `pop_item` removes the most recent, and a writer-computed sequence
    would race between concurrently running members.
    """

    __tablename__ = "team_session_items"
    __table_args__ = ({"postgresql_partition_by": "RANGE (created_at)"},)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True)
    workspace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True)
    #: Null for the orchestrator's own branch. Per-member branches keep a
    #: parallel topology's concurrent members from reading each other's
    #: partial reasoning.
    agent_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), default=None)
    #: One SDK `TResponseInputItem`, stored opaquely — the shape belongs
    #: to the pinned SDK version, not to AgentVerse.
    item: Mapped[dict[str, Any]] = mapped_column(JSONB)


# --- MCP integrations (Phase 6) ----------------------------------------
# Two layers: `mcp_servers` is the platform-wide catalog of what *could*
# be installed; `installed_servers` is a workspace's installation of one.
# Adding support for a service is a catalog row, not a module (ADR-0010).


class McpServerModel(Base):
    """The marketplace catalog. Deliberately **not** workspace-scoped.

    A tenant-owned table without `workspace_id` is normally a bug
    (CLAUDE.md §8). This is one of the explicit exceptions — the catalog
    is platform data, the same for every tenant — and it is called out
    in ADR-0010 so the exemption is a recorded decision, not an omission.
    """

    __tablename__ = "mcp_servers"
    __table_args__ = (UniqueConstraint("slug", name="uq_mcp_server_slug"),)

    id: Mapped[str] = _uuid_pk()
    slug: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text, index=True)
    transport: Mapped[McpTransport] = mapped_column(
        SqlEnum(McpTransport, name="mcp_transport", values_callable=lambda e: [m.value for m in e])
    )
    availability: Mapped[McpAvailability] = mapped_column(
        SqlEnum(
            McpAvailability,
            name="mcp_availability",
            values_callable=lambda e: [m.value for m in e],
        )
    )
    auth_scheme: Mapped[AuthScheme] = mapped_column(
        SqlEnum(AuthScheme, name="mcp_auth_scheme", values_callable=lambda e: [m.value for m in e])
    )
    #: STDIO entries only, and always from this row — never user input.
    #: A user-supplied command would be remote code execution on the
    #: worker fleet with extra steps (ADR-0010).
    command: Mapped[str | None] = mapped_column(Text, default=None)
    command_args: Mapped[list[str]] = mapped_column(JSONB, default=list)
    endpoint_url: Mapped[str | None] = mapped_column(Text, default=None)
    required_credentials: Mapped[list[str]] = mapped_column(JSONB, default=list)
    oauth_scopes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    documentation_url: Mapped[str | None] = mapped_column(Text, default=None)
    icon_slug: Mapped[str | None] = mapped_column(Text, default=None)
    is_deprecated: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class InstalledServerModel(Base):
    __tablename__ = "installed_servers"

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    #: Null for a custom user-registered server. RESTRICT because
    #: removing a catalog entry a workspace has installed must fail
    #: loudly rather than orphan the installation.
    mcp_server_id: Mapped[str | None] = mapped_column(
        ForeignKey("mcp_servers.id", ondelete="RESTRICT"), default=None
    )
    display_name: Mapped[str] = mapped_column(Text)
    transport: Mapped[McpTransport] = mapped_column(
        SqlEnum(McpTransport, name="mcp_transport", create_type=False)
    )
    endpoint_url: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[InstallStatus] = mapped_column(
        SqlEnum(
            InstallStatus, name="mcp_install_status", values_callable=lambda e: [m.value for m in e]
        ),
        default=InstallStatus.PENDING_AUTH,
    )
    health: Mapped[HealthStatus] = mapped_column(
        SqlEnum(
            HealthStatus, name="mcp_health_status", values_callable=lambda e: [m.value for m in e]
        ),
        default=HealthStatus.UNKNOWN,
    )
    #: Non-secret settings only. Secrets live in `credentials`, encrypted
    #: — anything here is readable by every endpoint returning a server.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    #: Cached discovery, so a run does not re-discover on every
    #: invocation (`mcp-expert`: cache tool discovery with a TTL).
    discovered_tools: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    tools_discovered_at: Mapped[datetime | None] = mapped_column(default=None)
    last_health_check_at: Mapped[datetime | None] = mapped_column(default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    version: Mapped[str | None] = mapped_column(Text, default=None)
    installed_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)


class ServerVersionModel(Base):
    """Recorded tool surface per version, so a breaking schema change on
    the server side surfaces as a detectable diff rather than a silent
    runtime failure (`mcp-expert`).
    """

    __tablename__ = "server_versions"

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True)
    installed_server_id: Mapped[str] = mapped_column(
        ForeignKey("installed_servers.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[str] = mapped_column(Text)
    tools: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    changed_tool_names: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime]


class CredentialModel(Base):
    """Envelope-encrypted third-party secrets.

    `ciphertext` is the secret encrypted under a per-row data key;
    `wrapped_dek` is that data key encrypted under a key from the runtime
    environment. A Postgres dump alone yields nothing usable.

    There is no plaintext column and no API path that returns one — not
    masked, not partial. `hint` is the last four characters only; a
    prefix would be a meaningful search key (ADR-0010).
    """

    __tablename__ = "credentials"
    __table_args__ = (
        UniqueConstraint("installed_server_id", "key", name="uq_credential_server_key"),
    )

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    installed_server_id: Mapped[str] = mapped_column(
        ForeignKey("installed_servers.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(Text)
    auth_scheme: Mapped[AuthScheme] = mapped_column(
        SqlEnum(AuthScheme, name="mcp_auth_scheme", create_type=False)
    )
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary)
    #: Identifies which environment key wrapped the DEK, so rotating the
    #: root key does not require re-encrypting every row at once.
    key_version: Mapped[str] = mapped_column(Text)
    hint: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(default=None)
    last_rotated_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class IntegrationPermissionModel(Base):
    """Which agent or team may use which server's tools, and how.

    Exactly one of `agent_id`/`team_id` is set, or neither for a
    workspace-wide grant. Enforced by a CHECK constraint rather than
    convention — "at most one" is the kind of invariant that decays.
    """

    __tablename__ = "permissions"
    __table_args__ = (
        CheckConstraint(
            "NOT (agent_id IS NOT NULL AND team_id IS NOT NULL)",
            name="ck_permission_single_subject",
        ),
    )

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    installed_server_id: Mapped[str] = mapped_column(
        ForeignKey("installed_servers.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), default=None
    )
    team_id: Mapped[str | None] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), default=None
    )
    level: Mapped[PermissionLevel] = mapped_column(
        SqlEnum(
            PermissionLevel,
            name="mcp_permission_level",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=PermissionLevel.READ_ONLY,
    )
    #: Empty means every discovered tool at this level. A non-empty list
    #: narrows further and maps to the SDK's own `ToolFilter`.
    allowed_tools: Mapped[list[str]] = mapped_column(JSONB, default=list)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    cache_ttl_seconds: Mapped[int] = mapped_column(Integer, default=0)
    max_calls_per_run: Mapped[int] = mapped_column(Integer, default=50)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    granted_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class ToolCallModel(Base):
    """Every tool invocation, recorded whether or not it ran.

    A blocked SSRF attempt that left no row would make the egress control
    unauditable, which is most of its value — hence `denied` and
    `circuit_open` as first-class statuses rather than silent drops.

    Partitioned by `created_at` from this, its first migration: this is
    the highest-volume table the phase adds (CLAUDE.md §8).
    """

    __tablename__ = "tool_calls"
    __table_args__ = ({"postgresql_partition_by": "RANGE (created_at)"},)

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    created_at: Mapped[datetime] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True)
    run_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), default=None)
    team_session_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), default=None)
    agent_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), default=None)
    installed_server_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), default=None)
    tool_name: Mapped[str] = mapped_column(Text)
    status: Mapped[ToolCallStatus] = mapped_column(
        SqlEnum(
            ToolCallStatus,
            name="tool_call_status",
            values_callable=lambda e: [m.value for m in e],
        )
    )
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB)
    #: Truncated to the output cap. The full result is never persisted —
    #: it is untrusted third-party content, and an unbounded store of it
    #: is both a cost and a liability (threat model T2).
    result_preview: Mapped[str | None] = mapped_column(Text, default=None)
    result_bytes: Mapped[int | None] = mapped_column(Integer, default=None)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    #: Which rule rejected a `denied` call — the permission rule or the
    #: egress rule. Null otherwise.
    denial_reason: Mapped[str | None] = mapped_column(Text, default=None)
    attempt: Mapped[int] = mapped_column(Integer, default=1)


class ToolLogModel(Base):
    """Free-form execution log lines attached to a tool call.

    Separate from `tool_calls` because one call can produce many lines
    (retries, redirect hops, circuit-breaker transitions) and folding
    them into the call row would mean an unbounded array column.
    """

    __tablename__ = "tool_logs"
    __table_args__ = ({"postgresql_partition_by": "RANGE (created_at)"},)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True)
    tool_call_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), default=None)
    installed_server_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), default=None)
    level: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class ToolMetricModel(Base):
    """Pre-aggregated per-tool statistics for the runtime dashboard.

    Rolled up rather than computed from `tool_calls` per page view: that
    table is partitioned and high-volume, and a p95 over it on every
    dashboard load is a scan nobody needs (CLAUDE.md §17).
    """

    __tablename__ = "tool_metrics"
    __table_args__ = (
        UniqueConstraint(
            "installed_server_id", "tool_name", "bucket_start", name="uq_tool_metric_bucket"
        ),
    )

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True)
    installed_server_id: Mapped[str] = mapped_column(
        ForeignKey("installed_servers.id", ondelete="CASCADE"), index=True
    )
    tool_name: Mapped[str] = mapped_column(Text)
    #: Hourly buckets. Fine enough for a latency chart, coarse enough
    #: that the table stays small.
    bucket_start: Mapped[datetime] = mapped_column(index=True)
    call_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    denied_count: Mapped[int] = mapped_column(Integer, default=0)
    timeout_count: Mapped[int] = mapped_column(Integer, default=0)
    total_duration_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    p95_duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)


class OauthSessionModel(Base):
    """A short-lived in-flight OAuth2 authorization-code exchange.

    Rows are deleted on completion, not kept: the PKCE verifier is itself
    a credential, and a stale one is a liability with no compensating
    value. `state` is unique so a replayed callback cannot match twice.
    """

    __tablename__ = "oauth_sessions"
    __table_args__ = (UniqueConstraint("state", name="uq_oauth_session_state"),)

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    installed_server_id: Mapped[str] = mapped_column(
        ForeignKey("installed_servers.id", ondelete="CASCADE"), index=True
    )
    #: CSRF token echoed by the provider on callback.
    state: Mapped[str] = mapped_column(Text)
    #: PKCE. Stored encrypted for the same reason the token is.
    code_verifier_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary)
    key_version: Mapped[str] = mapped_column(Text)
    redirect_uri: Mapped[str] = mapped_column(Text)
    requested_scopes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    started_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    #: Short — an authorization code exchange that has not completed in
    #: minutes is abandoned, and the row is a live credential.
    expires_at: Mapped[datetime]
    created_at: Mapped[datetime]


class WorkspaceIntegrationModel(Base):
    """Workspace-level defaults for an installed server.

    Distinct from `permissions`: a permission is a grant to a subject,
    this is the workspace's own policy for the server as a whole (is it
    on, who may grant it further, is it shared with teams).
    """

    __tablename__ = "workspace_integrations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "installed_server_id", name="uq_workspace_integration"),
    )

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    installed_server_id: Mapped[str] = mapped_column(
        ForeignKey("installed_servers.id", ondelete="CASCADE"), index=True
    )
    is_enabled: Mapped[bool] = mapped_column(default=True)
    #: When false, only an admin may grant this server to an agent.
    members_may_grant: Mapped[bool] = mapped_column(default=False)
    default_level: Mapped[PermissionLevel] = mapped_column(
        SqlEnum(PermissionLevel, name="mcp_permission_level", create_type=False),
        default=PermissionLevel.READ_ONLY,
    )
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class TeamIntegrationModel(Base):
    """A team's shared access to an installed server.

    Separate from a per-agent permission so a team can share one
    credential and one tool surface across its members without granting
    each member's agent individually (the brief's "shared credentials /
    shared tools" requirement).
    """

    __tablename__ = "team_integrations"
    __table_args__ = (
        UniqueConstraint("team_id", "installed_server_id", name="uq_team_integration"),
    )

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    installed_server_id: Mapped[str] = mapped_column(
        ForeignKey("installed_servers.id", ondelete="CASCADE"), index=True
    )
    #: When true, every member inherits the team's grant. When false,
    #: only members with their own per-agent grant may use it.
    shared_with_all_members: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime]


# --- Workflows (Phase 10) ------------------------------------------------
# Mirrors the `agents`/`agent_versions` split. Status/type/node-type
# columns are TEXT + CHECK, not a Postgres ENUM (this repo's standing
# preference for anything likely to grow a value — `ALTER TYPE ... DROP
# VALUE` does not exist, and Phase 4's `run_step_type` ENUM already
# needed a follow-up migration just to add one value).


class WorkflowModel(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(Text, default="draft")
    # No FK to workflow_versions here for the same reason `agents.
    # published_version_id` has none: that table's own FK back to
    # `workflows` must exist first. Added post-creation via the
    # migration's ALTER TABLE.
    published_version_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), nullable=True, default=None
    )
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class WorkflowVersionModel(Base):
    __tablename__ = "workflow_versions"
    __table_args__ = (
        UniqueConstraint("workflow_id", "version_number", name="uq_workflow_version"),
    )

    id: Mapped[str] = _uuid_pk()
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime]


class WorkflowNodeModel(Base):
    __tablename__ = "workflow_nodes"
    __table_args__ = (
        CheckConstraint(
            "(type = 'agent_step' AND agent_id IS NOT NULL AND team_id IS NULL) OR "
            "(type = 'team_step' AND team_id IS NOT NULL AND agent_id IS NULL) OR "
            "(type NOT IN ('agent_step', 'team_step') AND agent_id IS NULL AND team_id IS NULL)",
            name="ck_workflow_nodes_target",
        ),
    )

    # Caller-supplied (canvas-assigned), not server-generated — an edge
    # must reference a node before the version row exists.
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    workflow_version_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(Text)
    position_x: Mapped[float] = mapped_column(default=0)
    position_y: Mapped[float] = mapped_column(default=0)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # RESTRICT: deleting an agent/team a published workflow depends on
    # must fail loudly rather than leaving a node that can never run —
    # same rule as `team_members.agent_id`.
    agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"), nullable=True, default=None
    )
    team_id: Mapped[str | None] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"), nullable=True, default=None
    )


class WorkflowEdgeModel(Base):
    __tablename__ = "workflow_edges"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    workflow_version_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="CASCADE"), index=True
    )
    from_node_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_nodes.id", ondelete="CASCADE"), index=True
    )
    to_node_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_nodes.id", ondelete="CASCADE"), index=True
    )
    #: `{"field", "operator", "value"}` — a simple comparison, no
    #: expression language. `None` is the default/else edge.
    condition: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, default=None)
    branch_order: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)


class WorkflowRunModel(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), index=True
    )
    # RESTRICT, not CASCADE: a run is a durable record of what actually
    # executed — the version it ran against must not silently disappear
    # out from under an audit trail (same rule as `agent_runs.
    # agent_version_id`).
    workflow_version_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(Text, default="queued")
    input: Mapped[dict[str, Any]] = mapped_column(JSONB)
    idempotency_key: Mapped[str | None] = mapped_column(Text, default=None)
    cost_micro_usd: Mapped[int | None] = mapped_column(BigInteger, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime]


class WorkflowNodeRunModel(Base):
    """Partitioned by `created_at` — the per-node execution trail on a
    DAG run is the highest-volume table this phase adds, matching
    `agent_run_steps`/`execution_events`'s treatment from their first
    migration.
    """

    __tablename__ = "workflow_node_runs"
    __table_args__ = (
        CheckConstraint(
            "approval_decision IS NULL OR approval_decision IN ('approved', 'rejected')",
            name="ck_workflow_node_runs_approval_decision",
        ),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    created_at: Mapped[datetime] = mapped_column(primary_key=True)
    workflow_run_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    # RESTRICT: a node belongs to an immutable published version, which
    # never has rows deleted from under a run that referenced it.
    node_id: Mapped[str] = mapped_column(ForeignKey("workflow_nodes.id", ondelete="RESTRICT"))
    agent_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="RESTRICT"), nullable=True, default=None
    )
    team_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("team_sessions.id", ondelete="RESTRICT"), nullable=True, default=None
    )
    status: Mapped[str] = mapped_column(Text, default="queued")
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, default=None)
    approval_decision: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    approved_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, default=None
    )
    approved_at: Mapped[datetime | None] = mapped_column(default=None)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)
