"""Stage 1 — query rewrite.

Deliberately deterministic and LLM-free at this phase. `rag-expert`'s
rule is that every stage earns its place by measured improvement on a
labeled eval set; an LLM rewrite adds a model call's latency and cost to
*every* retrieval, so it is not shipped before the Phase 5 eval set can
show it pays for itself. What is here instead is the cheap, provably
useful part: normalizing the query for the vector arm and producing a
separate keyword-arm query, because the two arms want different things.

The vector arm wants the full natural-language question — embeddings
encode intent, and stripping stopwords from "how do I cancel my
subscription" degrades the embedding. The keyword arm wants the content
terms, because Postgres FTS ranks on term overlap and question scaffold
words ("how", "do", "I") match everything and rank nothing.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

#: Words that carry no retrieval signal in an English question. Short and
#: conservative on purpose: an over-aggressive list strips domain terms
#: ("can" in "can bus", "it" in "it department") and silently breaks
#: recall for exactly the queries hardest to notice being broken.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "do", "does", "did",
        "for", "from", "had", "has", "have", "how", "i", "in", "is", "it", "its",
        "me", "my", "of", "on", "or", "our", "please", "so", "that", "the", "their",
        "them", "then", "there", "these", "they", "this", "to", "was", "were", "what",
        "when", "where", "which", "who", "why", "will", "with", "would", "you", "your",
    }
)  # fmt: skip

_WHITESPACE = re.compile(r"\s+")
_KEYWORD_TOKEN = re.compile(r"[\w][\w'\-\.]*", re.UNICODE)

#: Guards the prompt-injection/cost blast radius of a free-text field
#: reaching an embedding call (CLAUDE.md §7). A query longer than this is
#: truncated, not rejected: a user pasting an essay should get degraded
#: retrieval, not an error.
MAX_QUERY_CHARS = 2000


@dataclass(frozen=True, slots=True)
class RewrittenQuery:
    """Both arms' inputs, derived from one user query.

    `keyword_query` can legitimately be empty — a query made entirely of
    stopwords ("what is it?") has no content terms. Callers must treat
    that as "skip the keyword arm", never as "search for everything".
    """

    original: str
    semantic_query: str
    keyword_query: str
    keywords: list[str]


def rewrite_query(query: str) -> RewrittenQuery:
    normalized = normalize_query(query)
    keywords = extract_keywords(normalized)
    return RewrittenQuery(
        original=query,
        semantic_query=normalized,
        keyword_query=" ".join(keywords),
        keywords=keywords,
    )


def normalize_query(query: str) -> str:
    """NFKC + whitespace collapse + length cap.

    NFKC folds the compatibility forms a copy-paste out of a PDF or a
    word processor introduces (full-width characters, ligatures, curly
    quotes' compatibility variants) so that a pasted query and a typed
    one embed to the same place.
    """
    normalized = unicodedata.normalize("NFKC", query)
    normalized = _WHITESPACE.sub(" ", normalized).strip()
    return normalized[:MAX_QUERY_CHARS]


def extract_keywords(query: str) -> list[str]:
    """Content terms for the FTS arm, de-duplicated, order preserved.

    Order is preserved rather than sorted so the resulting query string
    is stable and human-readable in a trace — a reviewer reading the
    trace event should recognize their own question in it.
    """
    seen: set[str] = set()
    keywords: list[str] = []
    for match in _KEYWORD_TOKEN.finditer(query):
        token = match.group(0).strip("-.'").lower()
        # Single characters are noise in FTS; they match everywhere.
        if len(token) < 2 or token in _STOPWORDS or token in seen:
            continue
        seen.add(token)
        keywords.append(token)
    return keywords
