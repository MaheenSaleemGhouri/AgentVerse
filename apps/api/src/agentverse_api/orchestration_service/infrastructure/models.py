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
from sqlalchemy import BigInteger, ForeignKey, Identity, Integer, Text, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from agentverse_api.infrastructure.orm_base import Base
from agentverse_api.orchestration_service.domain.agent_entities import AgentStatus
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
