"""Value types the retrieval pipeline passes between stages.

Citation metadata (`document_id`, `chunk_id`, `chunk_index`) is carried
on the chunk itself from the moment it leaves storage, so no stage can
"lose" it and no later stage has to re-look-up where a piece of context
came from (CLAUDE.md §9; `rag-expert`).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """One candidate from either retrieval arm.

    `score` means different things per arm (cosine distance converted to
    similarity for the vector arm, `ts_rank_cd` for the keyword arm), so
    it is never compared *across* arms — fusion ranks by position, not by
    score. It is kept for observability and for the reranker's
    tie-breaking only.
    """

    chunk_id: str
    kb_document_id: str
    knowledge_base_id: str
    workspace_id: str
    chunk_index: int
    content: str
    token_count: int
    score: float


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    """A chunk after fusion/reranking, carrying how it got there.

    `vector_rank`/`keyword_rank` are 1-based positions in each arm, or
    `None` when that arm did not return the chunk at all. Kept because
    "why did this chunk surface?" is a question the trace UI and the eval
    harness both need answered, and recomputing it later is impossible.
    """

    chunk: RetrievedChunk
    fused_score: float
    vector_rank: int | None
    keyword_rank: int | None


@dataclass(frozen=True, slots=True)
class Citation:
    """What the answer points back to. Deliberately minimal: an id triple
    the API layer can resolve to a filename/URL, not a denormalized copy
    of document metadata that would go stale.
    """

    chunk_id: str
    kb_document_id: str
    knowledge_base_id: str
    chunk_index: int


@dataclass(frozen=True, slots=True)
class AssembledContext:
    """The final product of the pipeline.

    `context_text` is what goes into the prompt; `citations` is the
    parallel list the UI renders. `dropped_chunk_count` is not cosmetic —
    a retrieval that silently discarded most of its candidates for budget
    reasons is a tuning signal, and hiding it is how "the answer got
    worse and nobody knows why" happens.
    """

    context_text: str
    citations: list[Citation]
    used_tokens: int
    budget_tokens: int
    dropped_chunk_count: int
    chunks: list[ScoredChunk] = field(default_factory=list)
