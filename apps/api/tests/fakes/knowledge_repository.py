"""In-memory `KnowledgeRepository` for route-level tests.

Stores every entity under its `workspace_id` and filters on it in every
read, exactly as the SQL implementation does — a fake that ignored
tenancy would make cross-workspace tests pass vacuously, which is worse
than not having them (CLAUDE.md §11).
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime

from agentverse_api.orchestration_service.domain.knowledge_entities import (
    DocumentStatus,
    KbDocument,
    KnowledgeBase,
)


def _now() -> datetime:
    return datetime.now(UTC)


class FakeKnowledgeRepository:
    def __init__(self) -> None:
        self.knowledge_bases: dict[str, KnowledgeBase] = {}
        self.documents: dict[str, KbDocument] = {}
        self.deleted_kb_ids: set[str] = set()
        self.deleted_document_ids: set[str] = set()

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
        kb = KnowledgeBase(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            name=name,
            description=description,
            embedding_model=embedding_model,
            embedding_model_version=embedding_model_version,
            created_by_user_id=created_by_user_id,
            created_at=_now(),
            updated_at=_now(),
        )
        self.knowledge_bases[kb.id] = kb
        return kb

    async def list_knowledge_bases(self, *, workspace_id: str) -> list[KnowledgeBase]:
        return [
            kb
            for kb in self.knowledge_bases.values()
            if kb.workspace_id == workspace_id and kb.id not in self.deleted_kb_ids
        ]

    async def get_knowledge_base(
        self, *, workspace_id: str, knowledge_base_id: str
    ) -> KnowledgeBase | None:
        kb = self.knowledge_bases.get(knowledge_base_id)
        if kb is None or kb.workspace_id != workspace_id or kb.id in self.deleted_kb_ids:
            return None
        return kb

    async def soft_delete_knowledge_base(
        self, *, workspace_id: str, knowledge_base_id: str
    ) -> bool:
        if await self.get_knowledge_base(
            workspace_id=workspace_id, knowledge_base_id=knowledge_base_id
        ):
            self.deleted_kb_ids.add(knowledge_base_id)
            for doc in self.documents.values():
                if doc.knowledge_base_id == knowledge_base_id:
                    self.deleted_document_ids.add(doc.id)
            return True
        return False

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
        document = KbDocument(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            knowledge_base_id=knowledge_base_id,
            storage_key=storage_key,
            original_filename=original_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            content_hash="",
            status=DocumentStatus.PENDING,
            error_message=None,
            chunk_count=0,
            created_at=_now(),
            updated_at=_now(),
        )
        self.documents[document.id] = document
        return document

    async def list_documents(
        self, *, workspace_id: str, knowledge_base_id: str
    ) -> list[KbDocument]:
        return [
            d
            for d in self.documents.values()
            if d.workspace_id == workspace_id
            and d.knowledge_base_id == knowledge_base_id
            and d.id not in self.deleted_document_ids
        ]

    async def get_document(self, *, workspace_id: str, document_id: str) -> KbDocument | None:
        doc = self.documents.get(document_id)
        if doc is None or doc.workspace_id != workspace_id or doc.id in self.deleted_document_ids:
            return None
        return doc

    async def sum_stored_bytes(self, *, workspace_id: str) -> int:
        return sum(
            doc.size_bytes
            for doc in self.documents.values()
            if doc.workspace_id == workspace_id and doc.id not in self.deleted_document_ids
        )

    async def soft_delete_document(self, *, workspace_id: str, document_id: str) -> bool:
        if await self.get_document(workspace_id=workspace_id, document_id=document_id):
            self.deleted_document_ids.add(document_id)
            return True
        return False

    async def reset_document_for_reindex(self, *, workspace_id: str, document_id: str) -> bool:
        doc = await self.get_document(workspace_id=workspace_id, document_id=document_id)
        if doc is None:
            return False
        self.documents[document_id] = replace(
            doc,
            content_hash="",
            status=DocumentStatus.PENDING,
            error_message=None,
            chunk_count=0,
            updated_at=_now(),
        )
        return True
