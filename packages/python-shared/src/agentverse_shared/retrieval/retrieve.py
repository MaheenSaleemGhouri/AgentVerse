"""Stage 2 — hybrid retrieve, then fuse.

Two arms run against the same candidate pool and their result *lists*
are combined with Reciprocal Rank Fusion. RRF is used rather than a
weighted score blend because the arms' scores are not commensurable:
cosine similarity lives in [0, 1] with most real values bunched near the
top, while `ts_rank_cd` is unbounded and corpus-dependent. Normalizing
them into a shared range requires corpus statistics we would have to
guess at, and guessing produces a blend that looks principled and is
not. RRF only reads *positions*, so it needs no such calibration.
"""

from __future__ import annotations

import asyncio

from agentverse_shared.retrieval.port import ChunkSearchPort
from agentverse_shared.retrieval.rewrite import RewrittenQuery
from agentverse_shared.retrieval.types import RetrievedChunk, ScoredChunk

#: The standard RRF damping constant (Cormack et al. 2009). Its job is to
#: stop rank 1 from dominating so heavily that the second arm can never
#: influence the outcome; 60 is the published default and is kept rather
#: than hand-tuned, because tuning it without an eval set is noise.
RRF_K = 60


async def hybrid_retrieve(
    *,
    search: ChunkSearchPort,
    rewritten: RewrittenQuery,
    embedding: list[float],
    workspace_id: str,
    knowledge_base_ids: list[str],
    embedding_model: str,
    embedding_model_version: str,
    limit: int,
) -> list[ScoredChunk]:
    """Runs both arms concurrently and fuses them.

    Each arm fetches `limit` candidates rather than `limit / 2`: fusion
    needs enough depth in each list for a chunk ranked mid-pack in one
    arm and top in the other to survive, which is the entire reason for
    running two arms.
    """
    if not knowledge_base_ids:
        return []

    vector_task = search.vector_search(
        workspace_id=workspace_id,
        knowledge_base_ids=knowledge_base_ids,
        embedding=embedding,
        embedding_model=embedding_model,
        embedding_model_version=embedding_model_version,
        limit=limit,
    )
    if rewritten.keyword_query:
        keyword_task = search.keyword_search(
            workspace_id=workspace_id,
            knowledge_base_ids=knowledge_base_ids,
            query=rewritten.keyword_query,
            embedding_model=embedding_model,
            embedding_model_version=embedding_model_version,
            limit=limit,
        )
        vector_hits, keyword_hits = await asyncio.gather(vector_task, keyword_task)
    else:
        # A query with no content terms ("what is it?") would make the
        # FTS arm match nothing useful; skipping it saves a query rather
        # than adding noise to the fusion.
        vector_hits = await vector_task
        keyword_hits = []

    return fuse_ranked_lists(vector_hits=vector_hits, keyword_hits=keyword_hits)


def fuse_ranked_lists(
    *,
    vector_hits: list[RetrievedChunk],
    keyword_hits: list[RetrievedChunk],
    k: int = RRF_K,
) -> list[ScoredChunk]:
    """Reciprocal Rank Fusion: score = Σ 1 / (k + rank) over the arms
    that returned the chunk. Pure — no I/O, exhaustively unit-testable.
    """
    vector_ranks = {hit.chunk_id: i for i, hit in enumerate(vector_hits, start=1)}
    keyword_ranks = {hit.chunk_id: i for i, hit in enumerate(keyword_hits, start=1)}

    # One canonical chunk object per id. The vector arm wins ties on the
    # object itself because its `score` is the one downstream diversity
    # logic reads; the content is identical either way.
    by_id: dict[str, RetrievedChunk] = {hit.chunk_id: hit for hit in keyword_hits}
    by_id.update({hit.chunk_id: hit for hit in vector_hits})

    fused: list[ScoredChunk] = []
    for chunk_id, chunk in by_id.items():
        v_rank = vector_ranks.get(chunk_id)
        kw_rank = keyword_ranks.get(chunk_id)
        score = 0.0
        if v_rank is not None:
            score += 1.0 / (k + v_rank)
        if kw_rank is not None:
            score += 1.0 / (k + kw_rank)
        fused.append(
            ScoredChunk(chunk=chunk, fused_score=score, vector_rank=v_rank, keyword_rank=kw_rank)
        )

    # `chunk_id` as the final tie-break keeps ordering deterministic:
    # dict order depends on insertion, and a retrieval that reordered
    # between two identical calls would make eval results irreproducible.
    fused.sort(key=lambda s: (-s.fused_score, s.chunk.chunk_id))
    return fused
