"""Narrow read/write access to the knowledge-base tables for the
ingestion job — not a general-purpose repository.

Mirrors `agents/repository.py`: a Protocol the job depends on, plus one
Postgres implementation, so unit tests substitute an in-memory fake
rather than needing a live database (CLAUDE.md §11).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_worker.knowledge.tables import (
    kb_chunks_table,
    kb_documents_table,
    knowledge_bases_table,
)


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    id: str
    workspace_id: str
    knowledge_base_id: str
    storage_key: str
    original_filename: str
    content_type: str
    status: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class KnowledgeBaseRecord:
    id: str
    workspace_id: str
    embedding_model: str
    embedding_model_version: str


@dataclass(frozen=True, slots=True)
class ChunkRow:
    id: str
    workspace_id: str
    knowledge_base_id: str
    kb_document_id: str
    chunk_index: int
    content: str
    token_count: int
    embedding: list[float]
    embedding_model: str
    embedding_model_version: str
    content_hash: str


class KnowledgeRepositoryProtocol(Protocol):
    async def get_document(self, document_id: str) -> DocumentRecord | None: ...
    async def get_knowledge_base(self, kb_id: str) -> KnowledgeBaseRecord | None: ...
    async def mark_processing(self, document_id: str) -> None: ...
    async def mark_indexed(
        self, *, document_id: str, chunk_count: int, content_hash: str
    ) -> None: ...
    async def mark_failed(self, *, document_id: str, error_message: str) -> None: ...
    async def count_chunks_for_hash(self, *, document_id: str, content_hash: str) -> int: ...
    async def delete_chunks(self, document_id: str) -> None: ...
    async def insert_chunks(self, chunks: list[ChunkRow]) -> int: ...


class WorkerKnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_document(self, document_id: str) -> DocumentRecord | None:
        result = await self._session.execute(
            select(
                kb_documents_table.c.id,
                kb_documents_table.c.workspace_id,
                kb_documents_table.c.knowledge_base_id,
                kb_documents_table.c.storage_key,
                kb_documents_table.c.original_filename,
                kb_documents_table.c.content_type,
                kb_documents_table.c.status,
                kb_documents_table.c.content_hash,
            ).where(
                kb_documents_table.c.id == document_id,
                # A document soft-deleted between enqueue and pickup must
                # not be re-indexed — the queue is at-least-once, so this
                # is a real ordering, not a hypothetical one.
                kb_documents_table.c.deleted_at.is_(None),
            )
        )
        row = result.one_or_none()
        return None if row is None else DocumentRecord(*row)

    async def get_knowledge_base(self, kb_id: str) -> KnowledgeBaseRecord | None:
        result = await self._session.execute(
            select(
                knowledge_bases_table.c.id,
                knowledge_bases_table.c.workspace_id,
                knowledge_bases_table.c.embedding_model,
                knowledge_bases_table.c.embedding_model_version,
            ).where(knowledge_bases_table.c.id == kb_id)
        )
        row = result.one_or_none()
        return None if row is None else KnowledgeBaseRecord(*row)

    async def mark_processing(self, document_id: str) -> None:
        await self._session.execute(
            update(kb_documents_table)
            .where(kb_documents_table.c.id == document_id)
            .values(status="processing", error_message=None, updated_at=datetime.now(UTC))
        )
        await self._session.commit()

    async def mark_indexed(self, *, document_id: str, chunk_count: int, content_hash: str) -> None:
        await self._session.execute(
            update(kb_documents_table)
            .where(kb_documents_table.c.id == document_id)
            .values(
                status="indexed",
                chunk_count=chunk_count,
                content_hash=content_hash,
                error_message=None,
                updated_at=datetime.now(UTC),
            )
        )
        await self._session.commit()

    async def mark_failed(self, *, document_id: str, error_message: str) -> None:
        await self._session.execute(
            update(kb_documents_table)
            .where(kb_documents_table.c.id == document_id)
            .values(
                status="failed",
                # Truncated: this string is surfaced in the UI, and an
                # unbounded provider/parser message could be enormous.
                error_message=error_message[:2000],
                updated_at=datetime.now(UTC),
            )
        )
        await self._session.commit()

    async def count_chunks_for_hash(self, *, document_id: str, content_hash: str) -> int:
        """Backs the idempotency check: chunks already written for this
        exact content mean a redelivered job has nothing to do.
        """
        result = await self._session.execute(
            select(func.count())
            .select_from(kb_chunks_table)
            .where(
                kb_chunks_table.c.kb_document_id == document_id,
                kb_chunks_table.c.content_hash == content_hash,
            )
        )
        return int(result.scalar_one())

    async def delete_chunks(self, document_id: str) -> None:
        await self._session.execute(
            delete(kb_chunks_table).where(kb_chunks_table.c.kb_document_id == document_id)
        )

    async def insert_chunks(self, chunks: list[ChunkRow]) -> int:
        """Bulk multi-row insert (CLAUDE.md §17: never a row-by-row loop).

        `ON CONFLICT DO NOTHING` against the
        `(kb_document_id, content_hash, chunk_index)` unique constraint
        makes a concurrent/redelivered writer a no-op instead of an
        integrity error — the DB is the final idempotency guarantee, not
        just the application-level pre-check.
        """
        if not chunks:
            return 0

        now = datetime.now(UTC)
        statement = pg_insert(kb_chunks_table).values(
            [
                {
                    "id": c.id,
                    "workspace_id": c.workspace_id,
                    "knowledge_base_id": c.knowledge_base_id,
                    "kb_document_id": c.kb_document_id,
                    "chunk_index": c.chunk_index,
                    "content": c.content,
                    "token_count": c.token_count,
                    "embedding": c.embedding,
                    "embedding_model": c.embedding_model,
                    "embedding_model_version": c.embedding_model_version,
                    "content_hash": c.content_hash,
                    "created_at": now,
                }
                for c in chunks
            ]
        )
        result = await self._session.execute(
            statement.on_conflict_do_nothing(constraint="uq_kb_chunk_document_hash_index")
        )
        await self._session.commit()
        # `rowcount` is a CursorResult attribute; `execute` is typed as
        # returning the broader `Result`. Reported rather than assumed
        # because the ON CONFLICT clause means inserted < len(chunks) is a
        # legitimate outcome (a concurrent delivery won the race).
        rowcount = getattr(result, "rowcount", None)
        return int(rowcount) if isinstance(rowcount, int) and rowcount >= 0 else len(chunks)
