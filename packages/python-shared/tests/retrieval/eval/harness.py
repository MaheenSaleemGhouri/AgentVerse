"""Scoring for the retrieval eval set.

Pure functions over id lists, so the metrics can be unit-tested against
hand-computed values rather than trusted because they look right. All
three are the standard definitions (`rag-expert`):

- **recall@k** — of the chunks a human marked relevant, what fraction
  made the top k. This is the metric that matters most for grounding: a
  relevant chunk that misses the cut simply cannot be cited.
- **precision@k** — of the top k, what fraction are relevant. Low
  precision spends context budget on noise, which pushes real evidence
  out of the window.
- **MRR** — how high the *first* relevant chunk ranks. Position matters
  because context is assembled in rank order, so an early relevant chunk
  survives budget truncation and a late one may not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DATASET_PATH = Path(__file__).parent / "dataset.json"


@dataclass(frozen=True, slots=True)
class EvalCase:
    query: str
    relevant_chunk_ids: frozenset[str]
    vector_hits: list[str]
    keyword_hits: list[str]


@dataclass(frozen=True, slots=True)
class EvalDataset:
    #: chunk_id -> (kb_document_id, content)
    corpus: dict[str, tuple[str, str]]
    cases: list[EvalCase]


def load_dataset(path: Path = DATASET_PATH) -> EvalDataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
    corpus = {c["chunk_id"]: (c["kb_document_id"], c["content"]) for c in raw["corpus"]}

    cases = []
    for case in raw["cases"]:
        unknown = (
            set(case["relevant_chunk_ids"]) | set(case["vector_hits"]) | set(case["keyword_hits"])
        ) - corpus.keys()
        if unknown:
            # A label referencing a chunk that isn't in the corpus would
            # silently depress recall forever, and the cause would be
            # invisible in the metric. Fail loudly at load instead.
            raise ValueError(f"case {case['query']!r} references unknown chunks: {sorted(unknown)}")
        cases.append(
            EvalCase(
                query=case["query"],
                relevant_chunk_ids=frozenset(case["relevant_chunk_ids"]),
                vector_hits=list(case["vector_hits"]),
                keyword_hits=list(case["keyword_hits"]),
            )
        )
    return EvalDataset(corpus=corpus, cases=cases)


def recall_at_k(retrieved: list[str], relevant: frozenset[str], k: int) -> float:
    if not relevant:
        return 1.0
    return len(set(retrieved[:k]) & relevant) / len(relevant)


def precision_at_k(retrieved: list[str], relevant: frozenset[str], k: int) -> float:
    top = retrieved[:k]
    if not top:
        return 0.0
    return len(set(top) & relevant) / len(top)


def reciprocal_rank(retrieved: list[str], relevant: frozenset[str]) -> float:
    for position, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in relevant:
            return 1.0 / position
    return 0.0


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
