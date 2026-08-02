"""The knowledge-base persistence port.

Every method takes `workspace_id` as a required argument and filters on
it — there is deliberately no "get by id" that skips tenancy. A caller
holding an id from another workspace gets `None`, which the router turns
into a 404 rather than a 403, so the resource's existence is not leaked
(CLAUDE.md §10, Rule 11).
"""

from __future__ import annotations

from typing import Protocol

from agentverse_api.orchestration_service.domain.knowledge_entities import (
    KbDocument,
    KnowledgeBase,
)


class KnowledgeRepository(Protocol):
    async def create_knowledge_base(
        self,
        *,
        workspace_id: str,
        name: str,
        description: str | None,
        embedding_model: str,
        embedding_model_version: str,
        created_by_user_id: str,
    ) -> KnowledgeBase: ...

    async def list_knowledge_bases(self, *, workspace_id: str) -> list[KnowledgeBase]: ...

    async def get_knowledge_base(
        self, *, workspace_id: str, knowledge_base_id: str
    ) -> KnowledgeBase | None: ...

    async def soft_delete_knowledge_base(
        self, *, workspace_id: str, knowledge_base_id: str
    ) -> bool: ...

    async def create_document(
        self,
        *,
        workspace_id: str,
        knowledge_base_id: str,
        storage_key: str,
        original_filename: str,
        content_type: str,
        size_bytes: int,
    ) -> KbDocument: ...

    async def list_documents(
        self, *, workspace_id: str, knowledge_base_id: str
    ) -> list[KbDocument]: ...

    async def get_document(self, *, workspace_id: str, document_id: str) -> KbDocument | None: ...

    async def sum_stored_bytes(self, *, workspace_id: str) -> int:
        """Total bytes of the workspace's live documents, for quota
        admission. Soft-deleted documents are excluded — an admin who
        deletes a file expects the space back.
        """
        ...

    async def soft_delete_document(self, *, workspace_id: str, document_id: str) -> bool: ...

    async def reset_document_for_reindex(self, *, workspace_id: str, document_id: str) -> bool:
        """Clears the stored `content_hash` and returns the document to
        `pending`.

        Clearing the hash is the point: ingestion short-circuits when the
        extracted content hashes to what is already indexed, so a reindex
        that left it in place would be a no-op. This is what makes
        "reindex" mean "redo the work" rather than "re-enqueue and skip".
        """
        ...
