"""The one `ChunkSearchPort` implementation, over `kb_chunks`.

Shared rather than written once per service for the same reason the
pipeline above it is shared: apps/api serves "test this knowledge base"
and apps/worker grounds the real run, and a search UI that ranks
differently from the agent is a debugging surface that lies.

Read-only, parameterized SQL against a table whose schema is owned by
apps/api's Alembic migrations. Nothing here defines or migrates the
table — Core column references only, so the shared package never becomes
a second source of truth for the schema (CLAUDE.md §8).

Every predicate that makes a query safe is non-optional in the signature
(see `port.py`): `workspace_id`, `knowledge_base_ids`, `embedding_model`,
`embedding_model_version`. There is no code path here that can run a
similarity query without all four.
"""

from __future__ import annotations

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_shared.retrieval.types import RetrievedChunk

#: Shared `WHERE` fragment. Written once so the two arms provably draw
#: from the same candidate pool — a divergence between them would make
#: rank fusion meaningless without producing any error.
_TENANT_FILTER = (
    "workspace_id = :workspace_id "
    "AND knowledge_base_id = ANY(:knowledge_base_ids) "
    "AND embedding_model = :embedding_model "
    "AND embedding_model_version = :embedding_model_version"
)

_SELECT_COLUMNS = (
    "id, kb_document_id, knowledge_base_id, workspace_id, chunk_index, content, token_count"
)

# `<=>` is pgvector's cosine *distance* (0 = identical). Converted to a
# similarity for the caller so `score` is consistently higher-is-better
# across both arms, and so a downstream threshold reads the way a reader
# expects. The ORDER BY stays on the raw distance operator because that
# is the expression the HNSW index (vector_cosine_ops) can serve.
_VECTOR_SQL = text(
    f"SELECT {_SELECT_COLUMNS}, 1 - (embedding <=> CAST(:embedding AS vector)) AS score "
    f"FROM kb_chunks WHERE {_TENANT_FILTER} "
    "ORDER BY embedding <=> CAST(:embedding AS vector) "
    "LIMIT :limit"
)

# `to_tsvector('english', content)` matches the expression the GIN index
# in the Phase 5 migration was built on — a different expression here
# (e.g. a different regconfig) would silently fall back to a sequential
# scan on a high-volume table. `plainto_tsquery` treats the input as
# literal terms, so a user query can never inject tsquery operators.
_KEYWORD_SQL = text(
    f"SELECT {_SELECT_COLUMNS}, "
    "ts_rank_cd(to_tsvector('english', content), plainto_tsquery('english', :query)) AS score "
    f"FROM kb_chunks WHERE {_TENANT_FILTER} "
    "AND to_tsvector('english', content) @@ plainto_tsquery('english', :query) "
    "ORDER BY score DESC, id "
    "LIMIT :limit"
)


class PostgresChunkSearch:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
        result = await self._session.execute(
            _VECTOR_SQL,
            {
                "workspace_id": workspace_id,
                "knowledge_base_ids": knowledge_base_ids,
                "embedding": _vector_literal(embedding),
                "embedding_model": embedding_model,
                "embedding_model_version": embedding_model_version,
                "limit": limit,
            },
        )
        return [_row_to_chunk(row) for row in result.all()]

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
        result = await self._session.execute(
            _KEYWORD_SQL,
            {
                "workspace_id": workspace_id,
                "knowledge_base_ids": knowledge_base_ids,
                "query": query,
                "embedding_model": embedding_model,
                "embedding_model_version": embedding_model_version,
                "limit": limit,
            },
        )
        return [_row_to_chunk(row) for row in result.all()]


def _vector_literal(embedding: list[float]) -> str:
    """pgvector's text input form. Built from floats we produced, never
    from user input, and passed as a bound parameter regardless.
    """
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


#: The column order both queries select, named once so the row unpacking
#: below cannot drift from the SQL above.
_ChunkRow = Row[tuple[str, str, str, str, int, str, int, float]]


def _row_to_chunk(row: _ChunkRow) -> RetrievedChunk:
    # `_t` is SQLAlchemy's documented typed-tuple accessor; the leading
    # underscore is their namespace-collision convention (a row's columns
    # are attributes), not a private API.
    chunk_id, document_id, kb_id, workspace_id, index, content, tokens, score = row._t  # noqa: SLF001
    return RetrievedChunk(
        chunk_id=chunk_id,
        kb_document_id=document_id,
        knowledge_base_id=kb_id,
        workspace_id=workspace_id,
        chunk_index=index,
        content=content,
        token_count=tokens,
        score=float(score),
    )
