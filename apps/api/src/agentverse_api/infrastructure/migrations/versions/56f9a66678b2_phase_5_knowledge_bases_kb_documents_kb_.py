"""phase 5: knowledge_bases, kb_documents, kb_chunks

Revision ID: 56f9a66678b2
Revises: 4387a581c5e4
Create Date: 2026-07-26 19:27:17.976421
"""

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision: str = "56f9a66678b2"
down_revision: Union[str, None] = "4387a581c5e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Matches EMBEDDING_DIMENSIONS[DEFAULT_EMBEDDING_MODEL] in
# orchestration_service/domain/knowledge_entities.py. Hardcoded here
# rather than imported: a migration is a historical record of the schema
# at this revision and must not silently change shape when application
# code later switches embedding model (which needs its own migration plus
# a backfill/cutover, per ADR-0003 and `vector-database-expert`).
_EMBEDDING_DIM = 1536


def upgrade() -> None:
    # pgvector on the primary Postgres instance per ADR-0003. The image
    # (`pgvector/pgvector:pg16`, infra/docker-compose.yml) ships the
    # extension; this enables it in *this* database. First real use of a
    # vector column in the codebase — Phase 0 deliberately deferred it.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- knowledge_bases ------------------------------------------------
    op.create_table(
        "knowledge_bases",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("embedding_model_version", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_knowledge_bases_workspace_id"), "knowledge_bases", ["workspace_id"], unique=False
    )
    op.create_index(
        "ix_knowledge_bases_workspace_created",
        "knowledge_bases",
        ["workspace_id", sa.text("created_at DESC")],
        unique=False,
    )

    # --- kb_documents ---------------------------------------------------
    op.create_table(
        "kb_documents",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "processing", "indexed", "failed", name="kb_document_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_kb_documents_workspace_id"), "kb_documents", ["workspace_id"], unique=False
    )
    op.create_index(
        op.f("ix_kb_documents_knowledge_base_id"),
        "kb_documents",
        ["knowledge_base_id"],
        unique=False,
    )
    op.create_index(
        "ix_kb_documents_kb_created",
        "kb_documents",
        ["knowledge_base_id", sa.text("created_at DESC")],
        unique=False,
    )
    # Partial index for the ingestion-queue view ("what's still being
    # processed in this workspace") — CLAUDE.md §8's narrow-hot-subset
    # pattern, same as Phase 4's ix_agent_runs_active.
    op.create_index(
        "ix_kb_documents_processing",
        "kb_documents",
        ["workspace_id"],
        unique=False,
        postgresql_where=sa.text("status IN ('pending', 'processing')"),
    )

    # --- kb_chunks ------------------------------------------------------
    op.create_table(
        "kb_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("kb_document_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(_EMBEDDING_DIM), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("embedding_model_version", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["kb_document_id"], ["kb_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "kb_document_id", "content_hash", "chunk_index", name="uq_kb_chunk_document_hash_index"
        ),
    )
    op.create_index(op.f("ix_kb_chunks_workspace_id"), "kb_chunks", ["workspace_id"], unique=False)
    op.create_index(
        op.f("ix_kb_chunks_knowledge_base_id"), "kb_chunks", ["knowledge_base_id"], unique=False
    )
    op.create_index(
        op.f("ix_kb_chunks_kb_document_id"), "kb_chunks", ["kb_document_id"], unique=False
    )
    # The btree index backing the *pre-filter* half of every retrieval
    # query. Retrieval always constrains
    # (workspace_id, knowledge_base_id, embedding_model, embedding_model_version)
    # before ranking by vector distance — CLAUDE.md §8 forbids
    # post-filtering an unscoped top-k, and mixing model versions in one
    # comparison produces meaningless scores.
    op.create_index(
        "ix_kb_chunks_retrieval_filter",
        "kb_chunks",
        ["workspace_id", "knowledge_base_id", "embedding_model", "embedding_model_version"],
        unique=False,
    )
    # HNSW over cosine distance per ADR-0003 and `vector-database-expert`
    # ("HNSW preferred for query-time recall/latency balance"; cosine used
    # consistently platform-wide). m/ef_construction left at pgvector's
    # defaults (16/64) — tuning them is a `postgresql-expert` follow-up
    # against real collection sizes and an eval set, not a guess now.
    op.create_index(
        "ix_kb_chunks_embedding_hnsw",
        "kb_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    # Keyword half of hybrid retrieval (`rag-expert`: semantic-only
    # retrieval buries exact-term matches). GIN over the same expression
    # the retrieval query uses, so Postgres can actually use it.
    op.execute(
        "CREATE INDEX ix_kb_chunks_content_fts ON kb_chunks "
        "USING gin (to_tsvector('english', content))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_kb_chunks_content_fts")
    op.drop_index("ix_kb_chunks_embedding_hnsw", table_name="kb_chunks")
    op.drop_index("ix_kb_chunks_retrieval_filter", table_name="kb_chunks")
    op.drop_index(op.f("ix_kb_chunks_kb_document_id"), table_name="kb_chunks")
    op.drop_index(op.f("ix_kb_chunks_knowledge_base_id"), table_name="kb_chunks")
    op.drop_index(op.f("ix_kb_chunks_workspace_id"), table_name="kb_chunks")
    op.drop_table("kb_chunks")

    op.drop_index("ix_kb_documents_processing", table_name="kb_documents")
    op.drop_index("ix_kb_documents_kb_created", table_name="kb_documents")
    op.drop_index(op.f("ix_kb_documents_knowledge_base_id"), table_name="kb_documents")
    op.drop_index(op.f("ix_kb_documents_workspace_id"), table_name="kb_documents")
    op.drop_table("kb_documents")
    sa.Enum("pending", "processing", "indexed", "failed", name="kb_document_status").drop(
        op.get_bind(), checkfirst=True
    )

    op.drop_index("ix_knowledge_bases_workspace_created", table_name="knowledge_bases")
    op.drop_index(op.f("ix_knowledge_bases_workspace_id"), table_name="knowledge_bases")
    op.drop_table("knowledge_bases")

    # The `vector` extension is deliberately NOT dropped: it is a
    # database-level object another schema could depend on, and dropping
    # it would cascade-destroy any vector column outside this migration's
    # ownership. Leaving it enabled is harmless and idempotent (upgrade
    # uses IF NOT EXISTS).
