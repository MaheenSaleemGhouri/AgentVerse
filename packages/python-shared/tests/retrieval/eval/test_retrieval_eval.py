"""Regression eval for the retrieval ranking stages.

This is the CI gate CLAUDE.md §9 asks for: every stage of the pipeline
earns its place by measured improvement on a labelled set, and a change
that degrades recall/precision/MRR fails the build instead of being
noticed months later by a user whose agent stopped citing the right
document.

Deliberately deterministic — no database, no embedding provider, no
LLM-as-judge. The two storage arms' output is supplied by the dataset
(what Postgres *would* return), so what is under measurement is the
fusion, reranking, and assembly logic AgentVerse owns. The SQL arms
themselves are covered by `tests/retrieval/integration`.

Groundedness here is structural, not semantic: every citation must
resolve to a chunk that was actually retrieved and whose text is
verbatim in the assembled context. Judging whether an *answer* is
grounded in that context is `prompt-engineer`'s eval harness and does
not belong in a fast pass/fail suite (CLAUDE.md §11).
"""

from __future__ import annotations

import pytest

from agentverse_shared.retrieval.assemble import assemble_context
from agentverse_shared.retrieval.rerank import rerank
from agentverse_shared.retrieval.retrieve import fuse_ranked_lists
from agentverse_shared.retrieval.types import RetrievedChunk, ScoredChunk
from tests.retrieval.eval.harness import (
    EvalCase,
    EvalDataset,
    load_dataset,
    mean,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

TOP_K = 5

#: Baselines measured against the current pipeline, set slightly below
#: the observed values so ordinary noise doesn't flap the build while a
#: real regression still trips it. Raise them when a change earns it —
#: that is the mechanism by which "this reranker is better" becomes a
#: claim with evidence rather than an assertion.
MIN_MEAN_RECALL_AT_5 = 0.95
MIN_MEAN_PRECISION_AT_5 = 0.30
MIN_MEAN_RECIPROCAL_RANK = 0.90


@pytest.fixture(scope="module")
def dataset() -> EvalDataset:
    return load_dataset()


def _rank(case: EvalCase, corpus: dict[str, tuple[str, str]], *, limit: int = TOP_K) -> list[str]:
    """Runs the real fusion + rerank stages over the case's arm outputs."""
    fused = fuse_ranked_lists(
        vector_hits=[_chunk(cid, corpus) for cid in case.vector_hits],
        keyword_hits=[_chunk(cid, corpus) for cid in case.keyword_hits],
    )
    return [s.chunk.chunk_id for s in rerank(fused, limit=limit)]


def _chunk(chunk_id: str, corpus: dict[str, tuple[str, str]]) -> RetrievedChunk:
    document_id, content = corpus[chunk_id]
    return RetrievedChunk(
        chunk_id=chunk_id,
        kb_document_id=document_id,
        knowledge_base_id="kb-eval",
        workspace_id="ws-eval",
        chunk_index=0,
        content=content,
        token_count=len(content.split()),
        score=0.5,
    )


class WordCounter:
    def count(self, text: str) -> int:
        return len(text.split())


def test_mean_recall_at_5_meets_the_baseline(dataset: EvalDataset) -> None:
    scores = [
        recall_at_k(_rank(case, dataset.corpus), case.relevant_chunk_ids, TOP_K)
        for case in dataset.cases
    ]
    assert mean(scores) >= MIN_MEAN_RECALL_AT_5, (
        f"recall@{TOP_K} regressed to {mean(scores):.3f}; "
        f"per-case: {dict(zip([c.query for c in dataset.cases], scores, strict=True))}"
    )


def test_mean_precision_at_5_meets_the_baseline(dataset: EvalDataset) -> None:
    scores = [
        precision_at_k(_rank(case, dataset.corpus), case.relevant_chunk_ids, TOP_K)
        for case in dataset.cases
    ]
    assert mean(scores) >= MIN_MEAN_PRECISION_AT_5


def test_mean_reciprocal_rank_meets_the_baseline(dataset: EvalDataset) -> None:
    scores = [
        reciprocal_rank(_rank(case, dataset.corpus), case.relevant_chunk_ids)
        for case in dataset.cases
    ]
    assert mean(scores) >= MIN_MEAN_RECIPROCAL_RANK


def test_every_case_surfaces_at_least_one_relevant_chunk(dataset: EvalDataset) -> None:
    """A per-case floor, not just an average.

    A mean can stay healthy while one query returns nothing useful, and
    that single query is a user whose agent answers ungrounded.
    """
    for case in dataset.cases:
        ranked = _rank(case, dataset.corpus)
        assert set(ranked) & case.relevant_chunk_ids, (
            f"no relevant chunk retrieved for {case.query!r}"
        )


def test_ranking_is_deterministic_across_repeated_runs(dataset: EvalDataset) -> None:
    """The metrics above are only meaningful if the same input produces
    the same ranking — a tie-break that varied per process would make
    every baseline above unfalsifiable.
    """
    for case in dataset.cases:
        assert _rank(case, dataset.corpus) == _rank(case, dataset.corpus)


def test_every_citation_resolves_to_text_present_in_the_assembled_context(
    dataset: EvalDataset,
) -> None:
    counter = WordCounter()
    for case in dataset.cases:
        fused = fuse_ranked_lists(
            vector_hits=[_chunk(cid, dataset.corpus) for cid in case.vector_hits],
            keyword_hits=[_chunk(cid, dataset.corpus) for cid in case.keyword_hits],
        )
        selected: list[ScoredChunk] = rerank(fused, limit=TOP_K)
        assembled = assemble_context(selected, budget_tokens=400, counter=counter)

        retrieved_ids = {s.chunk.chunk_id for s in selected}
        for citation in assembled.citations:
            # A citation the model could not have drawn from is a
            # fabricated source — the exact failure citations exist to
            # rule out.
            assert citation.chunk_id in retrieved_ids
            assert dataset.corpus[citation.chunk_id][1] in assembled.context_text


def test_dropped_chunks_never_leave_a_citation_behind(dataset: EvalDataset) -> None:
    """Budget truncation must remove the citation with the text.

    A citation pointing at a chunk that was dropped for size would name a
    source the model never saw.
    """
    counter = WordCounter()
    case = dataset.cases[0]
    fused = fuse_ranked_lists(
        vector_hits=[_chunk(cid, dataset.corpus) for cid in case.vector_hits],
        keyword_hits=[_chunk(cid, dataset.corpus) for cid in case.keyword_hits],
    )
    # A budget that fits roughly one block, forcing drops.
    assembled = assemble_context(rerank(fused, limit=TOP_K), budget_tokens=40, counter=counter)

    assert assembled.dropped_chunk_count > 0
    assert len(assembled.citations) == len(assembled.chunks)
    for citation in assembled.citations:
        assert dataset.corpus[citation.chunk_id][1] in assembled.context_text
