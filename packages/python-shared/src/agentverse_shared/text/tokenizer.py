"""Token counting.

Lives in the shared package because two services need the *identical*
count, not merely a compatible one: apps/worker sizes chunks at
ingestion, apps/api computes the remaining context budget at retrieval.
If those two disagreed, a chunk sized as "500 tokens" at write time
could overflow the budget it was measured against at read time.

`rag-expert` forbids character-count approximation for budgeting, so the
real BPE tokenizer is the default. It is wrapped behind `TokenCounter`
so pure chunking logic never depends on tiktoken directly — tiktoken
fetches and caches its encoding files on first use (real I/O), which
must not sit inside a domain-layer pure function (CLAUDE.md §5).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

import tiktoken

#: Encoding used by the gpt-4o / gpt-4.1 family and by
#: `text-embedding-3-*`. Named explicitly rather than resolved per model
#: so a model string we haven't seen can't silently pick a different
#: tokenizer and change chunk boundaries.
DEFAULT_ENCODING = "o200k_base"


class TokenCounter(Protocol):
    """How chunking and context assembly measure text length.

    A Protocol, not a concrete class, so tests can inject a trivial
    deterministic counter (e.g. whitespace words) and assert exact chunk
    boundaries without depending on BPE specifics or network access.
    """

    def count(self, text: str) -> int: ...


class TiktokenCounter:
    """Production `TokenCounter`. Encoding load is cached process-wide —
    it is an expensive, network-touching first call.
    """

    def __init__(self, encoding_name: str = DEFAULT_ENCODING) -> None:
        self._encoding_name = encoding_name

    def count(self, text: str) -> int:
        return len(_encoding(self._encoding_name).encode(text))


@lru_cache(maxsize=4)
def _encoding(name: str) -> tiktoken.Encoding:
    return tiktoken.get_encoding(name)
