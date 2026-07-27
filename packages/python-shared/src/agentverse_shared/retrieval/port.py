"""The storage port the pipeline retrieves through.

The pipeline itself is pure and storage-agnostic; every implementation
(apps/api's SQLAlchemy adapter, apps/worker's Core-table adapter, tests'
in-memory fake) satisfies this Protocol.

The tenancy and embedding-identity parameters are on the *port*, not
left to each implementation to remember. `workspace_id`,
`embedding_model`, and `embedding_model_version` are required arguments
precisely so that an adapter cannot be written that "forgot" to filter —
CLAUDE.md Rule 11 (tenant isolation is absolute) and §8 (never mix
embedding-model versions in one similarity search) are enforced by the
signature rather than by reviewer vigilance.
"""

from __future__ import annotations

from typing import Protocol

from agentverse_shared.retrieval.types import RetrievedChunk


class ChunkSearchPort(Protocol):
    async def vector_search(
        self,
        *,
        workspace_id: str,
        knowledge_base_ids: list[str],
        embedding: list[float],
        embedding_model: str,
        embedding_model_version: str,
        limit: int,
    ) -> list[RetrievedChunk]:
        """Nearest neighbours by cosine distance, best first.

        Implementations must PRE-filter on `workspace_id` inside the SQL
        (a `WHERE` alongside the `ORDER BY ... <=> ...`), never take an
        unscoped top-k and drop foreign rows afterwards: post-filtering
        both leaks tenant data through timing/ordering and destroys
        recall, since the k slots get consumed by other tenants' chunks.
        """
        ...

    async def keyword_search(
        self,
        *,
        workspace_id: str,
        knowledge_base_ids: list[str],
        query: str,
        embedding_model: str,
        embedding_model_version: str,
        limit: int,
    ) -> list[RetrievedChunk]:
        """Full-text matches, best first. Same pre-filter requirement.

        Filtered by embedding model/version too — not because keyword
        matching depends on the embedding, but because the two arms must
        draw from exactly the same candidate pool for fusion to be
        meaningful. A chunk the vector arm structurally cannot return
        must not enter through the keyword arm.
        """
        ...
