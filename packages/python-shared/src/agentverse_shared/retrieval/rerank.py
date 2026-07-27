"""Stage 3 — rerank.

What this is *not*: a cross-encoder. A trained reranker is the stage
that usually buys the most precision, but it is a second model call per
retrieval, and `rag-expert`'s rule is that a stage ships only once a
labeled eval set shows it earns its latency and cost. That measurement
belongs to the Phase 5 eval work, so this module is deliberately a pure,
zero-I/O reranker and the cross-encoder is a documented follow-up rather
than a half-wired dependency (CLAUDE.md §16: no speculative scaffolding).

What it *is*: relevance-preserving diversification. Fusion routinely
returns five near-identical chunks — adjacent chunks of one document
overlap by design (the chunker emits a 50–100 token overlap), so a
document that matches well tends to occupy the entire top-k and crowd
out a second document that also answers the question. Spending the
context budget on five paraphrases of one passage is strictly worse than
spending it on three passages from three sources, and it is also what
makes a grounded answer cite one document when it should cite several.
"""

from __future__ import annotations

import re

from agentverse_shared.retrieval.types import ScoredChunk

_TOKEN = re.compile(r"\w+", re.UNICODE)

#: How much a candidate's score is discounted per unit of similarity to
#: the chunks already selected. At 0.0 this module is a pass-through; at
#: 1.0 diversity fully overrides relevance. 0.5 keeps relevance dominant
#: — a near-duplicate has to be *very* close to lose to a weaker chunk.
DEFAULT_DIVERSITY_WEIGHT = 0.5

#: Ceiling on chunks contributed by any single document, applied only
#: while other documents still have candidates. Without it, a
#: 400-page manual monopolizes every result for every query against a
#: knowledge base that also contains short, precise documents.
DEFAULT_MAX_PER_DOCUMENT = 3


def rerank(
    candidates: list[ScoredChunk],
    *,
    limit: int,
    diversity_weight: float = DEFAULT_DIVERSITY_WEIGHT,
    max_per_document: int = DEFAULT_MAX_PER_DOCUMENT,
) -> list[ScoredChunk]:
    """Greedy MMR-style selection over the fused candidates.

    Returns at most `limit` chunks, best first. Pure and deterministic:
    given the same candidate list it always returns the same selection,
    which is what makes the eval harness's numbers reproducible.
    """
    if limit <= 0 or not candidates:
        return []
    if diversity_weight <= 0.0:
        return candidates[:limit]

    remaining = list(candidates)
    selected: list[ScoredChunk] = []
    selected_tokens: list[frozenset[str]] = []
    per_document: dict[str, int] = {}

    while remaining and len(selected) < limit:
        # The per-document cap is a preference, not a hard wall: if every
        # remaining candidate comes from a capped document, taking one is
        # still better than returning fewer chunks than asked for.
        eligible = [
            c for c in remaining if per_document.get(c.chunk.kb_document_id, 0) < max_per_document
        ] or remaining

        # `min` on a negated score rather than `max`, so the secondary key
        # can be the chunk id ascending — matching fusion's tie-break.
        # (`max` would need the id negated, which strings don't support,
        # and hashing it instead would make ordering vary between
        # processes under hash randomization, breaking eval repeatability.)
        best = min(
            eligible,
            key=lambda c: (
                -_adjusted_score(c, selected_tokens, diversity_weight),
                c.chunk.chunk_id,
            ),
        )
        selected.append(best)
        selected_tokens.append(_tokenize(best.chunk.content))
        per_document[best.chunk.kb_document_id] = per_document.get(best.chunk.kb_document_id, 0) + 1
        remaining.remove(best)

    return selected


def _adjusted_score(
    candidate: ScoredChunk, selected_tokens: list[frozenset[str]], diversity_weight: float
) -> float:
    if not selected_tokens:
        return candidate.fused_score
    tokens = _tokenize(candidate.chunk.content)
    redundancy = max(_jaccard(tokens, other) for other in selected_tokens)
    return candidate.fused_score * (1.0 - diversity_weight * redundancy)


def _tokenize(text: str) -> frozenset[str]:
    """Lexical token set for the redundancy measure.

    Lexical rather than embedding-based on purpose: a true MMR would
    compare candidate embeddings, but the retrieval port does not return
    vectors (returning 1536 floats per candidate purely to compare them
    against each other is a large, pointless payload). Near-duplicate
    chunks from an overlapping chunker are lexically near-identical, so
    the cheap measure catches the case this stage exists to catch.
    """
    return frozenset(m.group(0).lower() for m in _TOKEN.finditer(text))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0
