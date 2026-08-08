"""Retrieval over the docs corpus.

Term-overlap scoring, not embeddings. That is a deliberate call for a
corpus of a few dozen passages: an embedding round-trip would add a
network call and a cost to every question, and would have to be
re-embedded on every docs edit, to beat a scorer that already resolves
"how do I rotate an API key" to the API-keys guide. `DocsIndex` is a port
precisely so this stays a swap, not a rewrite, when the corpus grows
(CLAUDE.md §9 — each retrieval stage earns its place by measured
improvement, and there is nothing to measure against yet).

The scoring function is pure and unit-tested; the class around it only
holds the loaded corpus.
"""

from __future__ import annotations

import re
from typing import Final

from agentverse_api.assistant_service.domain.entities import DocPassage
from agentverse_api.assistant_service.infrastructure.docs_corpus import load_passages

_WORD: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")

# Words that appear in almost every question and almost every passage.
# Left in, they let "how do I do the thing" match everything equally.
_STOPWORDS: Final[frozenset[str]] = frozenset(
    """a an and are as at be by can do does for from how i if in is it my of on or
    that the there this to use using was what when where which why with you your""".split()
)

TITLE_WEIGHT: Final[int] = 6
HEADING_WEIGHT: Final[int] = 4
BODY_WEIGHT: Final[int] = 1
MIN_SCORE: Final[int] = 2
"""Below this, a passage matched on one incidental word. Returning it
would ground the answer in something irrelevant, which reads as a
confident non-sequitur — worse than "I could not find that"."""


def terms(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.lower()) if word not in _STOPWORDS}


def score(query_terms: set[str], passage: DocPassage) -> int:
    """Weighted overlap: where a term matches matters more than how often.

    Frequency is deliberately ignored. A passage that says "webhook"
    twenty times is not twice as relevant as one that says it ten times,
    but it would score twice as high, and long passages would win every
    query.
    """
    if not query_terms:
        return 0
    title = terms(passage.doc_title)
    heading = terms(passage.heading)
    body = terms(passage.text)
    return (
        TITLE_WEIGHT * len(query_terms & title)
        + HEADING_WEIGHT * len(query_terms & heading)
        + BODY_WEIGHT * len(query_terms & body)
    )


def rank(query: str, passages: list[DocPassage], *, limit: int) -> list[DocPassage]:
    query_terms = terms(query)
    scored = [
        (score(query_terms, passage), index, passage) for index, passage in enumerate(passages)
    ]
    # `index` breaks ties by corpus order, which is path order — so the
    # same question always assembles the same context. Non-determinism
    # here would make an answer irreproducible for no benefit.
    ranked = sorted(
        (entry for entry in scored if entry[0] >= MIN_SCORE),
        key=lambda entry: (-entry[0], entry[1]),
    )
    return [passage for _, _, passage in ranked[:limit]]


class CorpusDocsIndex:
    """`DocsIndex` over the committed corpus, loaded once per process."""

    def __init__(self, passages: list[DocPassage] | None = None) -> None:
        self._passages = passages if passages is not None else load_passages()

    def search(self, query: str, *, limit: int) -> list[DocPassage]:
        return rank(query, self._passages, limit=limit)
