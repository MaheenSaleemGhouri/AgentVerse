"""SQLAlchemy Core tables mirroring apps/api's authoritative knowledge-base
schema (`orchestration_service/infrastructure/models.py`, migration
`56f9a66678b2`).

Same "shared wire contract, not shared code" pattern as
`agents/tables.py`: apps/api's Alembic migrations own the schema; this
worker reads/writes the columns it needs via Core. Both sides update in
lockstep against the migration, never against each other's source.
"""

from __future__ import annotations

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, MetaData, Table, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import UUID

metadata = MetaData()

kb_document_status_enum = postgresql.ENUM(
    "pending",
    "processing",
    "indexed",
    "failed",
    name="kb_document_status",
    create_type=False,
)

#: Must equal apps/api's EMBEDDING_DIMENSIONS[DEFAULT_EMBEDDING_MODEL] and
#: the migration's column width. A mismatch is a write-time failure, not a
#: silent one, but keeping the constant here documented avoids guessing.
EMBEDDING_DIM = 1536

knowledge_bases_table = Table(
    "knowledge_bases",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("name", Text),
    Column("embedding_model", Text),
    Column("embedding_model_version", Text),
    Column("deleted_at", DateTime(timezone=True)),
)

kb_documents_table = Table(
    "kb_documents",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("knowledge_base_id", UUID(as_uuid=False), ForeignKey("knowledge_bases.id")),
    Column("storage_key", Text),
    Column("original_filename", Text),
    Column("content_type", Text),
    Column("size_bytes", BigInteger),
    Column("content_hash", Text),
    Column("status", kb_document_status_enum),
    Column("error_message", Text),
    Column("chunk_count", Integer),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
    Column("deleted_at", DateTime(timezone=True)),
)

kb_chunks_table = Table(
    "kb_chunks",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("knowledge_base_id", UUID(as_uuid=False), ForeignKey("knowledge_bases.id")),
    Column("kb_document_id", UUID(as_uuid=False), ForeignKey("kb_documents.id")),
    Column("chunk_index", Integer),
    Column("content", Text),
    Column("token_count", Integer),
    Column("embedding", Vector(EMBEDDING_DIM)),
    Column("embedding_model", Text),
    Column("embedding_model_version", Text),
    Column("content_hash", Text),
    Column("created_at", DateTime(timezone=True)),
)
