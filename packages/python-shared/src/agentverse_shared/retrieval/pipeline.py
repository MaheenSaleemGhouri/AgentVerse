"""The four stages composed into one call.

Lives in the shared package for the same reason the embedding provider
does: apps/api serves the "test your knowledge base" search endpoint and
apps/worker grounds the actual agent run. If those two ranked
differently, the search UI would confidently show a user results their
agent never sees — a debugging surface that lies is worse than no
debugging surface (CLAUDE.md Rule 3).

Note on `CLAUDE.md` §5's "vector DB access is encapsulated behind the
agent-runtime fleet": that rule scopes a *separate* vector store as an
independent datastore. ADR-0003 put vectors in the primary Postgres via
pgvector, so `kb_chunks` is an ordinary table of the orchestration
service's own schema — apps/api reading it is a service reading its own
database, not a cross-service reach. Nothing here queries another
service's store.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_shared.embeddings.port import EmbeddingProvider
from agentverse_shared.retrieval.assemble import assemble_context
from agentverse_shared.retrieval.port import ChunkSearchPort
from agentverse_shared.retrieval.rerank import (
    DEFAULT_DIVERSITY_WEIGHT,
    DEFAULT_MAX_PER_DOCUMENT,
    rerank,
)
from agentverse_shared.retrieval.retrieve import hybrid_retrieve
from agentverse_shared.retrieval.rewrite import rewrite_query
from agentverse_shared.retrieval.types import AssembledContext
from agentverse_shared.text.tokenizer import TokenCounter

#: How many candidates each arm fetches before reranking. Wider than the
#: final `top_k` on purpose — reranking can only reorder what retrieval
#: handed it, so a narrow first pass caps quality no matter how good the
#: reranker is.
DEFAULT_CANDIDATE_LIMIT = 40

#: Chunks that survive reranking and are offered to assembly. Assembly
#: may still drop some for budget.
DEFAULT_TOP_K = 8


class EmbeddingIdentityMismatchError(RuntimeError):
    """The configured embedder does not produce the vectors this
    knowledge base was indexed with.

    Fails loudly instead of searching anyway: mixing embedding-model
    versions in one similarity search throws no error and returns no
    empty result — it just quietly returns worse matches, which is the
    exact silent degradation `vector-database-expert` calls out and the
    hardest class of RAG bug to notice in production.
    """


@dataclass(frozen=True, slots=True)
class RetrievalConfig:
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT
    top_k: int = DEFAULT_TOP_K
    diversity_weight: float = DEFAULT_DIVERSITY_WEIGHT
    max_per_document: int = DEFAULT_MAX_PER_DOCUMENT


async def retrieve_context(
    *,
    query: str,
    workspace_id: str,
    knowledge_base_ids: list[str],
    embedding_model: str,
    embedding_model_version: str,
    budget_tokens: int,
    search: ChunkSearchPort,
    embedder: EmbeddingProvider,
    counter: TokenCounter,
    config: RetrievalConfig | None = None,
) -> AssembledContext:
    """rewrite → hybrid retrieve → rerank → assemble.

    `workspace_id` is a required argument threaded to the storage port
    rather than resolved anywhere inside this module — it always comes
    from the caller's authenticated identity, never from a request body
    (CLAUDE.md Rule 6/11).

    Raises `EmbeddingError` (the shared taxonomy) if the query cannot be
    embedded; grounding silently degrading to an ungrounded answer would
    violate the transparency the citations exist to provide.
    """
    cfg = config or RetrievalConfig()

    rewritten = rewrite_query(query)
    if not rewritten.semantic_query or not knowledge_base_ids:
        return _empty(budget_tokens)

    # The query is embedded with the *knowledge base's* model identity,
    # not the process default: a KB mid-backfill still has chunks under
    # its old model, and a query embedded with the new one would be
    # compared against vectors from a different space.
    embedded = await embedder.embed([rewritten.semantic_query])
    if embedded.model != embedding_model or embedded.model_version != embedding_model_version:
        raise EmbeddingIdentityMismatchError(
            f"Knowledge base expects {embedding_model}@{embedding_model_version} "
            f"but the configured embedder produces {embedded.model}@{embedded.model_version}"
        )

    fused = await hybrid_retrieve(
        search=search,
        rewritten=rewritten,
        embedding=embedded.vectors[0],
        workspace_id=workspace_id,
        knowledge_base_ids=knowledge_base_ids,
        embedding_model=embedding_model,
        embedding_model_version=embedding_model_version,
        limit=cfg.candidate_limit,
    )
    reranked = rerank(
        fused,
        limit=cfg.top_k,
        diversity_weight=cfg.diversity_weight,
        max_per_document=cfg.max_per_document,
    )
    return assemble_context(reranked, budget_tokens=budget_tokens, counter=counter)


def _empty(budget_tokens: int) -> AssembledContext:
    return AssembledContext(
        context_text="",
        citations=[],
        used_tokens=0,
        budget_tokens=budget_tokens,
        dropped_chunk_count=0,
        chunks=[],
    )
