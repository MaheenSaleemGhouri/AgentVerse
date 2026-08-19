"""Hybrid (semantic + keyword) marketplace catalog search.

Mirrors the *shape* of `agentverse_shared.retrieval.pipeline` — rewrite
-> dual-arm retrieve -> fuse — with listing-shaped types and none of
that pipeline's token-budget/citation-assembly machinery, which exists
to ground an LLM's answer in RAG and has no analogue here: a marketplace
search result is a catalog card, not an assembled context string
(docs/adr/0016).

Reciprocal Rank Fusion over each arm's *position*, not its raw score,
for the same reason RAG's `retrieve.py` gives: cosine similarity and
`ts_rank_cd` are not on comparable scales, and normalizing them would
require corpus statistics this module has no principled way to guess.

**Graceful degradation is the whole point of this module existing
separately from a hard-failing RAG-style pipeline.** A knowledge-base
query that cannot be embedded is a grounding failure worth surfacing
(`EmbeddingIdentityMismatchError`); a catalog page that cannot run its
vector arm is not — it must never go blank because the embedding
backfill has not reached a listing yet, or because the embedding
provider is briefly unavailable. Every failure mode here falls back to
the keyword arm alone.
"""

from __future__ import annotations

import contextlib

from agentverse_shared.embeddings.port import EmbeddingError, EmbeddingProvider
from agentverse_shared.retrieval.rewrite import rewrite_query
from agentverse_shared.search import SearchMatch, to_prefix_tsquery

from agentverse_api.marketplace_service.domain.ports import ListingSearchFilters, ListingSearchPort

#: The standard RRF damping constant (Cormack et al. 2009) — kept at the
#: published default rather than hand-tuned, same rationale as RAG's
#: `retrieve.py`: tuning it without a labeled eval set is noise.
RRF_K = 60

#: Candidates each arm fetches before fusion. Wider than any realistic
#: page size so a listing ranked mid-pack in one arm and top in the
#: other still survives — the entire reason to run two arms.
DEFAULT_CANDIDATE_LIMIT = 40


async def hybrid_search(
    *,
    query: str,
    filters: ListingSearchFilters,
    search: ListingSearchPort,
    embedder: EmbeddingProvider,
    limit: int = DEFAULT_CANDIDATE_LIMIT,
) -> list[SearchMatch]:
    """Every fused candidate, best first — up to `limit`.

    The caller (`MarketplaceService.browse`) is responsible for paging
    this ranked list and re-hydrating full `Listing` rows for the page
    it wants; this function only ranks.
    """
    rewritten = rewrite_query(query)

    keyword_hits: list[SearchMatch] = []
    tsquery = to_prefix_tsquery(rewritten.keyword_query) if rewritten.keyword_query else None
    if tsquery is not None:
        keyword_hits = await search.keyword_search(
            tsquery=tsquery, filters=filters, limit=DEFAULT_CANDIDATE_LIMIT
        )

    vector_hits: list[SearchMatch] = []
    if rewritten.semantic_query:
        embedded = None
        # Degrade to the keyword arm alone on failure rather than fail
        # the request — see the module docstring.
        with contextlib.suppress(EmbeddingError):
            embedded = await embedder.embed([rewritten.semantic_query])
        if embedded is not None:
            vector_hits = await search.vector_search(
                embedding=embedded.vectors[0],
                embedding_model=embedded.model,
                embedding_model_version=embedded.model_version,
                filters=filters,
                limit=DEFAULT_CANDIDATE_LIMIT,
            )

    return fuse_search_matches(vector_hits=vector_hits, keyword_hits=keyword_hits, limit=limit)


def fuse_search_matches(
    *, vector_hits: list[SearchMatch], keyword_hits: list[SearchMatch], limit: int
) -> list[SearchMatch]:
    """Reciprocal Rank Fusion over both arms' result lists. Pure — no
    I/O, exhaustively unit-testable — and public rather than a private
    helper precisely so it is: `SearchMatch.id` is a listing's slug
    (both arms key on it identically), so it doubles as the fusion key.
    """
    vector_ranks = {hit.id: i for i, hit in enumerate(vector_hits, start=1)}
    keyword_ranks = {hit.id: i for i, hit in enumerate(keyword_hits, start=1)}

    # One canonical match per id. The vector arm wins ties on the object
    # itself — its `rank` is replaced by the fused score below either
    # way, so this only decides which arm's (identical) title/subtitle
    # text is kept.
    by_id: dict[str, SearchMatch] = {hit.id: hit for hit in keyword_hits}
    by_id.update({hit.id: hit for hit in vector_hits})

    fused: list[tuple[float, SearchMatch]] = []
    for listing_id, match in by_id.items():
        score = 0.0
        if listing_id in vector_ranks:
            score += 1.0 / (RRF_K + vector_ranks[listing_id])
        if listing_id in keyword_ranks:
            score += 1.0 / (RRF_K + keyword_ranks[listing_id])
        fused.append((score, match))

    # `id` as the final tie-break keeps ordering deterministic between
    # identical calls.
    fused.sort(key=lambda pair: (-pair[0], pair[1].id))
    return [
        SearchMatch(id=match.id, title=match.title, subtitle=match.subtitle, rank=score)
        for score, match in fused[:limit]
    ]
