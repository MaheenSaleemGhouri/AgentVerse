"""Pure unit tests: RRF fusion and the graceful-degradation branches of
`hybrid_search`, all against fakes — no I/O, no real Postgres.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from agentverse_shared.embeddings.port import (
    EmbeddingError,
    EmbeddingRateLimitError,
    EmbeddingResult,
)
from agentverse_shared.search import SearchMatch

from agentverse_api.marketplace_service.application.hybrid_marketplace_search import (
    fuse_search_matches,
    hybrid_search,
)
from agentverse_api.marketplace_service.domain.ports import ListingSearchFilters


def _match(listing_id: str, *, rank: float = 1.0) -> SearchMatch:
    return SearchMatch(id=listing_id, title=listing_id, subtitle="a listing", rank=rank)


class TestFuse:
    def test_a_listing_both_arms_agree_on_outranks_a_single_arm_hit(self) -> None:
        fused = fuse_search_matches(
            vector_hits=[_match("a"), _match("b")],
            keyword_hits=[_match("b"), _match("a")],
            limit=10,
        )
        # "b" is rank 2 in vector / rank 1 in keyword; "a" is rank 1 /
        # rank 2 — RRF sums 1/(k+rank) over both arms, so a listing found
        # by *both* arms strictly beats one found by only one, all else
        # equal.
        assert [m.id for m in fused] == ["a", "b"]

    def test_a_hit_in_only_one_arm_still_survives(self) -> None:
        fused = fuse_search_matches(vector_hits=[_match("only-vector")], keyword_hits=[], limit=10)
        assert [m.id for m in fused] == ["only-vector"]

    def test_ties_break_on_id_for_determinism(self) -> None:
        # "zzz" is rank 1 in vector / rank 2 in keyword; "aaa" is rank 2
        # in vector / rank 1 in keyword — the *sum* of RRF terms is
        # identical either way round, so this is a genuine tie, and the
        # id tiebreak is what keeps repeated calls from reordering it.
        fused = fuse_search_matches(
            vector_hits=[_match("zzz"), _match("aaa")],
            keyword_hits=[_match("aaa"), _match("zzz")],
            limit=10,
        )
        assert [m.id for m in fused] == ["aaa", "zzz"]

    def test_the_result_is_capped_at_limit(self) -> None:
        hits = [_match(f"listing-{i}") for i in range(5)]
        fused = fuse_search_matches(vector_hits=hits, keyword_hits=[], limit=2)
        assert len(fused) == 2

    def test_no_hits_from_either_arm_is_an_empty_list_not_an_error(self) -> None:
        assert fuse_search_matches(vector_hits=[], keyword_hits=[], limit=10) == []


@dataclass
class _FakeSearch:
    vector_hits: list[SearchMatch] = field(default_factory=list)
    keyword_hits: list[SearchMatch] = field(default_factory=list)
    vector_calls: list[dict[str, object]] = field(default_factory=list)
    keyword_calls: list[dict[str, object]] = field(default_factory=list)

    async def vector_search(self, **kwargs: object) -> list[SearchMatch]:
        self.vector_calls.append(kwargs)
        return self.vector_hits

    async def keyword_search(self, **kwargs: object) -> list[SearchMatch]:
        self.keyword_calls.append(kwargs)
        return self.keyword_hits


@dataclass
class _FakeEmbedder:
    vector: list[float] = field(default_factory=lambda: [0.1, 0.2, 0.3])
    raises: Exception | None = None
    calls: list[list[str]] = field(default_factory=list)

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        self.calls.append(texts)
        if self.raises is not None:
            raise self.raises
        return EmbeddingResult(
            vectors=[self.vector for _ in texts],
            model="text-embedding-3-small",
            model_version="1",
            prompt_tokens=len(texts),
        )

    @property
    def model(self) -> str:
        return "text-embedding-3-small"

    @property
    def model_version(self) -> str:
        return "1"

    @property
    def dimensions(self) -> int:
        return len(self.vector)


class TestHybridSearch:
    async def test_both_arms_are_queried_and_fused(self) -> None:
        search = _FakeSearch(
            vector_hits=[_match("semantic-match")], keyword_hits=[_match("keyword-match")]
        )
        results = await hybrid_search(
            query="automate my support inbox",
            filters=ListingSearchFilters(),
            search=search,
            embedder=_FakeEmbedder(),
        )
        assert {m.id for m in results} == {"semantic-match", "keyword-match"}
        assert len(search.vector_calls) == 1
        assert len(search.keyword_calls) == 1

    async def test_an_embedding_provider_failure_degrades_to_keyword_only(self) -> None:
        """The core promise of this module: a vector-arm failure must
        never fail the whole search — it must fall back to whatever the
        keyword arm found.
        """
        search = _FakeSearch(keyword_hits=[_match("still-found")])
        embedder = _FakeEmbedder(raises=EmbeddingRateLimitError("rate limited"))
        results = await hybrid_search(
            query="anything", filters=ListingSearchFilters(), search=search, embedder=embedder
        )
        assert [m.id for m in results] == ["still-found"]
        assert search.vector_calls == []

    async def test_an_unexpected_embedder_exception_is_not_swallowed(self) -> None:
        """Only the shared `EmbeddingError` taxonomy is a degrade-and-
        continue signal (CLAUDE.md §9) — anything else is a real bug and
        must not be silently absorbed into "no vector results".
        """
        search = _FakeSearch(keyword_hits=[_match("irrelevant")])
        embedder = _FakeEmbedder(raises=RuntimeError("boom"))
        with pytest.raises(RuntimeError, match="boom"):
            await hybrid_search(
                query="anything", filters=ListingSearchFilters(), search=search, embedder=embedder
            )

    async def test_a_stopword_only_query_skips_the_keyword_arm_but_still_embeds(self) -> None:
        search = _FakeSearch(vector_hits=[_match("semantic-only")])
        results = await hybrid_search(
            query="what is it",
            filters=ListingSearchFilters(),
            search=search,
            embedder=_FakeEmbedder(),
        )
        assert [m.id for m in results] == ["semantic-only"]
        assert search.keyword_calls == []

    async def test_filters_are_threaded_to_both_arms_unchanged(self) -> None:
        search = _FakeSearch()
        filters = ListingSearchFilters(category_slug="research", free_only=True)
        await hybrid_search(
            query="research agent", filters=filters, search=search, embedder=_FakeEmbedder()
        )
        assert search.vector_calls[0]["filters"] is filters
        assert search.keyword_calls[0]["filters"] is filters


def test_embedding_error_is_importable_from_the_shared_taxonomy() -> None:
    # Guards the module boundary this test file's degrade/re-raise
    # assertions depend on: `EmbeddingError` must stay the base of the
    # taxonomy `hybrid_search` catches.
    assert issubclass(EmbeddingRateLimitError, EmbeddingError)
