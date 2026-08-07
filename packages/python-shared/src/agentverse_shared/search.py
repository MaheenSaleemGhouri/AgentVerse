"""The vocabulary of full-text search, shared by every context that owns
something searchable.

Four bounded contexts hold searchable rows — agents, knowledge bases and
teams in orchestration, listings in the marketplace — and each builds its
own query against its own tables. What they must agree on is how a user's
raw typing becomes a Postgres `tsquery`: four copies of that translation
would drift, and a drifted translation shows up as "search finds it in
the palette but not in the catalog", which is indistinguishable from a
bug in the data.

So the translation lives here, once (Rule 3), and the per-context
repositories differ only in which columns they search.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

#: Below this, a prefix query matches most of the workspace and ranks
#: nothing usefully — the caller should show its idle state instead.
MIN_QUERY_LENGTH: Final[int] = 2

#: Anything longer is a paste, not a search. Capped rather than rejected
#: so a stray paste degrades to a search for its first words.
MAX_QUERY_LENGTH: Final[int] = 128

#: `tsquery` cost grows with term count and a typeahead never needs many.
MAX_TERMS: Final[int] = 8

#: Postgres text-search configuration. Named explicitly rather than left
#: to `default_text_search_config`, which is a per-database setting: a
#: query relying on the default would silently stop matching the index
#: (built with this literal) if the server's default ever differed.
TEXT_SEARCH_CONFIG: Final[str] = "english"

_TERM_PATTERN: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9]+")


@dataclass(frozen=True, slots=True)
class SearchMatch:
    """One row a context is willing to expose to search.

    Deliberately not the full entity: search returns enough to render a
    result and navigate to it, and the caller fetches the rest through
    that entity's own endpoint. Returning whole agents here would make
    search a second, unversioned read path for every entity it covers.
    """

    id: str
    title: str
    subtitle: str | None
    #: `ts_rank_cd` output. Comparable *within* one kind; across kinds it
    #: is only a tiebreaker, since the ranks come from different columns.
    rank: float


def to_prefix_tsquery(raw: str) -> str | None:
    """Turn what a user typed into a prefix-matching `tsquery` string.

    Returns `None` when there is nothing worth querying — the caller
    should skip the round trip rather than search for everything.

    Every term gets Postgres's `:*` prefix operator, because this backs a
    typeahead: someone who has typed "knowl" expects their knowledge base,
    and `websearch_to_tsquery` would look for the whole word "knowl" and
    find nothing. Terms are ANDed, so each keystroke narrows.

    **This is injection-safe by construction, not by escaping.** The only
    thing that survives `_TERM_PATTERN` is ASCII alphanumerics, so no
    `tsquery` operator (`&`, `|`, `!`, `<->`, quotes, parentheses) can
    reach `to_tsquery`. That matters because `to_tsquery` — unlike
    `plainto_tsquery` — parses its argument as an expression, and a
    caller passing raw input to it would let a user craft one.
    """
    terms = _TERM_PATTERN.findall(raw[:MAX_QUERY_LENGTH])[:MAX_TERMS]
    if not terms:
        return None
    return " & ".join(f"{term.lower()}:*" for term in terms)


def is_searchable(raw: str) -> bool:
    """Whether `raw` has enough signal to be worth a query at all."""
    return len(raw.strip()) >= MIN_QUERY_LENGTH and to_prefix_tsquery(raw) is not None
