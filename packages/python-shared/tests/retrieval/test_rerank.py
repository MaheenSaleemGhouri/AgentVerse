from __future__ import annotations

from agentverse_shared.retrieval.rerank import rerank
from agentverse_shared.retrieval.types import ScoredChunk
from tests.retrieval.conftest import chunk


def scored(
    chunk_id: str, score: float, *, content: str = "unique text here", document_id: str = "doc-1"
) -> ScoredChunk:
    return ScoredChunk(
        chunk=chunk(chunk_id, content=content, document_id=document_id),
        fused_score=score,
        vector_rank=1,
        keyword_rank=None,
    )


def test_returns_at_most_the_limit_best_first() -> None:
    result = rerank(
        [
            scored("a", 0.9, content="alpha"),
            scored("b", 0.5, content="beta"),
            scored("c", 0.1, content="gamma"),
        ],
        limit=2,
    )
    assert [s.chunk.chunk_id for s in result] == ["a", "b"]


def test_empty_candidates_and_zero_limit_are_handled() -> None:
    assert rerank([], limit=5) == []
    assert rerank([scored("a", 0.9)], limit=0) == []


def test_zero_diversity_weight_is_a_pass_through() -> None:
    candidates = [scored("a", 0.9, content="same"), scored("b", 0.8, content="same")]
    assert rerank(candidates, limit=2, diversity_weight=0.0) == candidates[:2]


def test_a_near_duplicate_loses_to_a_weaker_but_distinct_chunk() -> None:
    """The stage's whole reason to exist: overlapping chunks from one
    document must not consume the entire context budget as paraphrases.
    """
    result = rerank(
        [
            scored("a", 0.90, content="the refund window is thirty days"),
            scored("dup", 0.85, content="the refund window is thirty days"),
            scored("other", 0.60, content="enterprise contracts renew annually"),
        ],
        limit=2,
        diversity_weight=0.9,
    )
    assert [s.chunk.chunk_id for s in result] == ["a", "other"]


def test_a_distinct_chunk_does_not_beat_a_clearly_stronger_one() -> None:
    # Diversity discounts relevance, it must not override it outright.
    result = rerank(
        [
            scored("strong", 0.90, content="alpha beta gamma"),
            scored("weak", 0.05, content="entirely different wording"),
        ],
        limit=1,
    )
    assert result[0].chunk.chunk_id == "strong"


def test_per_document_cap_makes_room_for_a_second_source() -> None:
    candidates = [
        scored(f"a{i}", 0.9 - i * 0.01, content=f"passage {i}", document_id="doc-a")
        for i in range(5)
    ]
    candidates.append(scored("b0", 0.2, content="other source", document_id="doc-b"))

    result = rerank(candidates, limit=4, max_per_document=3)

    doc_ids = [s.chunk.kb_document_id for s in result]
    assert doc_ids.count("doc-a") == 3
    assert "doc-b" in doc_ids


def test_cap_is_a_preference_not_a_wall_when_only_one_document_has_candidates() -> None:
    """Returning fewer chunks than asked for, when more relevant chunks
    exist, would be worse than exceeding the cap.
    """
    candidates = [
        scored(f"a{i}", 0.9 - i * 0.01, content=f"passage {i}", document_id="doc-a")
        for i in range(5)
    ]
    result = rerank(candidates, limit=5, max_per_document=2)
    assert len(result) == 5


def test_selection_is_deterministic_across_calls() -> None:
    candidates = [scored("b", 0.5, content="same words"), scored("a", 0.5, content="same words")]
    assert [s.chunk.chunk_id for s in rerank(candidates, limit=2)] == [
        s.chunk.chunk_id for s in rerank(list(reversed(candidates)), limit=2)
    ]
