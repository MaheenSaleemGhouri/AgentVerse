from __future__ import annotations

from agentverse_shared.retrieval.retrieve import RRF_K, fuse_ranked_lists, hybrid_retrieve
from agentverse_shared.retrieval.rewrite import rewrite_query
from tests.retrieval.conftest import FakeSearch, chunk


def test_fusion_scores_a_single_arm_hit_by_its_reciprocal_rank() -> None:
    fused = fuse_ranked_lists(vector_hits=[chunk("c1")], keyword_hits=[])
    assert fused[0].fused_score == 1.0 / (RRF_K + 1)
    assert fused[0].vector_rank == 1
    assert fused[0].keyword_rank is None


def test_a_chunk_found_by_both_arms_outranks_either_arms_top_hit() -> None:
    """The entire point of hybrid retrieval: agreement between a semantic
    and a lexical match is stronger evidence than either alone.
    """
    fused = fuse_ranked_lists(
        vector_hits=[chunk("only-vector"), chunk("both")],
        keyword_hits=[chunk("only-keyword"), chunk("both")],
    )
    assert fused[0].chunk.chunk_id == "both"
    assert fused[0].vector_rank == 2
    assert fused[0].keyword_rank == 2


def test_fusion_deduplicates_chunks_present_in_both_arms() -> None:
    fused = fuse_ranked_lists(vector_hits=[chunk("c1")], keyword_hits=[chunk("c1")])
    assert [s.chunk.chunk_id for s in fused] == ["c1"]


def test_fusion_ordering_is_deterministic_on_ties() -> None:
    # Same rank in the same single arm -> identical scores; ordering must
    # still be stable or eval numbers become irreproducible.
    a = fuse_ranked_lists(vector_hits=[], keyword_hits=[chunk("b"), chunk("a")])
    b = fuse_ranked_lists(vector_hits=[], keyword_hits=[chunk("b"), chunk("a")])
    assert [s.chunk.chunk_id for s in a] == [s.chunk.chunk_id for s in b]


def test_fusion_uses_positions_not_raw_scores() -> None:
    """A keyword arm's `ts_rank_cd` can be orders of magnitude larger than
    a cosine similarity; fusion must ignore magnitude entirely.
    """
    fused = fuse_ranked_lists(
        vector_hits=[chunk("v", score=0.99)],
        keyword_hits=[chunk("k", score=999.0)],
    )
    assert fused[0].fused_score == fused[1].fused_score


async def test_hybrid_retrieve_runs_both_arms_and_prefilters_by_tenant() -> None:
    search = FakeSearch(vector_hits=[chunk("v1")], keyword_hits=[chunk("k1")])

    await hybrid_retrieve(
        search=search,
        rewritten=rewrite_query("cancel subscription"),
        embedding=[0.1],
        workspace_id="ws-1",
        knowledge_base_ids=["kb-1"],
        embedding_model="text-embedding-3-small",
        embedding_model_version="1",
        limit=10,
    )

    for call in (search.vector_calls[0], search.keyword_calls[0]):
        assert call["workspace_id"] == "ws-1"
        assert call["knowledge_base_ids"] == ["kb-1"]
        assert call["embedding_model"] == "text-embedding-3-small"
        assert call["embedding_model_version"] == "1"


async def test_hybrid_retrieve_skips_the_keyword_arm_without_content_terms() -> None:
    search = FakeSearch(vector_hits=[chunk("v1")])

    await hybrid_retrieve(
        search=search,
        rewritten=rewrite_query("what is it?"),
        embedding=[0.1],
        workspace_id="ws-1",
        knowledge_base_ids=["kb-1"],
        embedding_model="m",
        embedding_model_version="1",
        limit=10,
    )

    assert len(search.vector_calls) == 1
    assert search.keyword_calls == []


async def test_hybrid_retrieve_returns_nothing_without_a_knowledge_base() -> None:
    search = FakeSearch(vector_hits=[chunk("v1")])

    result = await hybrid_retrieve(
        search=search,
        rewritten=rewrite_query("anything"),
        embedding=[0.1],
        workspace_id="ws-1",
        knowledge_base_ids=[],
        embedding_model="m",
        embedding_model_version="1",
        limit=10,
    )

    assert result == []
    assert search.vector_calls == []


async def test_each_arm_fetches_the_full_limit_not_half() -> None:
    """Fusion needs depth in both lists; halving each arm would drop the
    mid-pack chunk that agreement is supposed to promote.
    """
    search = FakeSearch(vector_hits=[chunk("v")], keyword_hits=[chunk("k")])

    await hybrid_retrieve(
        search=search,
        rewritten=rewrite_query("cancel subscription"),
        embedding=[0.1],
        workspace_id="ws-1",
        knowledge_base_ids=["kb-1"],
        embedding_model="m",
        embedding_model_version="1",
        limit=40,
    )

    assert search.vector_calls[0]["limit"] == 40
    assert search.keyword_calls[0]["limit"] == 40
