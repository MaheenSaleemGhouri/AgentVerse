"""Postgres implementation of `domain/ports/knowledge_repository.py`.

In its own module rather than appended to `repositories.py`: that file
already owns agents and runs, and knowledge bases are a separate
aggregate with a separate lifecycle. Splitting on the aggregate keeps
each file readable (CLAUDE.md §16).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.infrastructure.sql_result import affected
from agentverse_api.orchestration_service.domain.knowledge_entities import (
    DocumentStatus,
    KbDocument,
    KnowledgeBase,
)
from agentverse_api.orchestration_service.infrastructure.models import (
    KbDocumentModel,
    KnowledgeBaseModel,
)


def _to_kb(row: KnowledgeBaseModel) -> KnowledgeBase:
    return KnowledgeBase(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        description=row.description,
        embedding_model=row.embedding_model,
        embedding_model_version=row.embedding_model_version,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_document(row: KbDocumentModel) -> KbDocument:
    return KbDocument(
        id=row.id,
        workspace_id=row.workspace_id,
        knowledge_base_id=row.knowledge_base_id,
        storage_key=row.storage_key,
        original_filename=row.original_filename,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        content_hash=row.content_hash,
        status=row.status,
        error_message=row.error_message,
        chunk_count=row.chunk_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlKnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_knowledge_base(
        self,
        *,
        workspace_id: str,
        name: str,
        description: str | None,
        embedding_model: str,
        embedding_model_version: str,
        created_by_user_id: str,
    ) -> KnowledgeBase:
        now = datetime.now(UTC)
        row = KnowledgeBaseModel(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            name=name,
            description=description,
            embedding_model=embedding_model,
            embedding_model_version=embedding_model_version,
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.commit()
        return _to_kb(row)

    async def list_knowledge_bases(self, *, workspace_id: str) -> list[KnowledgeBase]:
        result = await self._session.execute(
            select(KnowledgeBaseModel)
            .where(
                KnowledgeBaseModel.workspace_id == workspace_id,
                KnowledgeBaseModel.deleted_at.is_(None),
            )
            .order_by(KnowledgeBaseModel.created_at.desc())
        )
        return [_to_kb(row) for row in result.scalars().all()]

    async def get_knowledge_base(
        self, *, workspace_id: str, knowledge_base_id: str
    ) -> KnowledgeBase | None:
        result = await self._session.execute(
            select(KnowledgeBaseModel).where(
                KnowledgeBaseModel.id == knowledge_base_id,
                # Tenancy is part of the lookup, not a check the caller
                # is trusted to remember afterwards.
                KnowledgeBaseModel.workspace_id == workspace_id,
                KnowledgeBaseModel.deleted_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        return None if row is None else _to_kb(row)

    async def soft_delete_knowledge_base(
        self, *, workspace_id: str, knowledge_base_id: str
    ) -> bool:
        now = datetime.now(UTC)
        result = await self._session.execute(
            update(KnowledgeBaseModel)
            .where(
                KnowledgeBaseModel.id == knowledge_base_id,
                KnowledgeBaseModel.workspace_id == workspace_id,
                KnowledgeBaseModel.deleted_at.is_(None),
            )
            .values(deleted_at=now, updated_at=now)
        )
        # Documents are soft-deleted with their knowledge base in the same
        # transaction: retrieval filters on the KB, but the documents list
        # would otherwise still show rows belonging to a deleted parent.
        await self._session.execute(
            update(KbDocumentModel)
            .where(
                KbDocumentModel.knowledge_base_id == knowledge_base_id,
                KbDocumentModel.workspace_id == workspace_id,
                KbDocumentModel.deleted_at.is_(None),
            )
            .values(deleted_at=now, updated_at=now)
        )
        await self._session.commit()
        return affected(result)

    async def create_document(
        self,
        *,
        workspace_id: str,
        knowledge_base_id: str,
        storage_key: str,
        original_filename: str,
        content_type: str,
        size_bytes: int,
    ) -> KbDocument:
        now = datetime.now(UTC)
        row = KbDocumentModel(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            knowledge_base_id=knowledge_base_id,
            storage_key=storage_key,
            original_filename=original_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            # Empty until the worker has extracted text and hashed it —
            # the hash is of the *extracted content*, not the raw upload,
            # so two encodings of the same document dedupe correctly.
            content_hash="",
            status=DocumentStatus.PENDING,
            error_message=None,
            chunk_count=0,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.commit()
        return _to_document(row)

    async def list_documents(
        self, *, workspace_id: str, knowledge_base_id: str
    ) -> list[KbDocument]:
        result = await self._session.execute(
            select(KbDocumentModel)
            .where(
                KbDocumentModel.workspace_id == workspace_id,
                KbDocumentModel.knowledge_base_id == knowledge_base_id,
                KbDocumentModel.deleted_at.is_(None),
            )
            .order_by(KbDocumentModel.created_at.desc())
        )
        return [_to_document(row) for row in result.scalars().all()]

    async def get_document(self, *, workspace_id: str, document_id: str) -> KbDocument | None:
        result = await self._session.execute(
            select(KbDocumentModel).where(
                KbDocumentModel.id == document_id,
                KbDocumentModel.workspace_id == workspace_id,
                KbDocumentModel.deleted_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        return None if row is None else _to_document(row)

    async def sum_stored_bytes(self, *, workspace_id: str) -> int:
        result = await self._session.execute(
            select(func.coalesce(func.sum(KbDocumentModel.size_bytes), 0)).where(
                KbDocumentModel.workspace_id == workspace_id,
                KbDocumentModel.deleted_at.is_(None),
            )
        )
        # `coalesce` makes the empty-workspace case 0 rather than NULL,
        # so callers never special-case "no documents yet".
        return int(result.scalar_one())

    async def soft_delete_document(self, *, workspace_id: str, document_id: str) -> bool:
        now = datetime.now(UTC)
        result = await self._session.execute(
            update(KbDocumentModel)
            .where(
                KbDocumentModel.id == document_id,
                KbDocumentModel.workspace_id == workspace_id,
                KbDocumentModel.deleted_at.is_(None),
            )
            .values(deleted_at=now, updated_at=now)
        )
        await self._session.commit()
        return affected(result)

    async def reset_document_for_reindex(self, *, workspace_id: str, document_id: str) -> bool:
        now = datetime.now(UTC)
        result = await self._session.execute(
            update(KbDocumentModel)
            .where(
                KbDocumentModel.id == document_id,
                KbDocumentModel.workspace_id == workspace_id,
                KbDocumentModel.deleted_at.is_(None),
            )
            .values(
                status=DocumentStatus.PENDING,
                # Clearing the hash is what makes a reindex actually redo
                # the work — ingestion short-circuits on an unchanged hash.
                content_hash="",
                error_message=None,
                chunk_count=0,
                updated_at=now,
            )
        )
        await self._session.commit()
        return affected(result)
