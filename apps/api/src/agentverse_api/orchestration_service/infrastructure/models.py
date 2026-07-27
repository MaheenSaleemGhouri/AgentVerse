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
from sqlalchemy import BigInteger, ForeignKey, Integer, Text, UniqueConstraint
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
