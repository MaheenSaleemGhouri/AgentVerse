"""The shape search returns."""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_shared.search import SearchMatch

from agentverse_api.search_service.domain.kinds import SearchKind


@dataclass(frozen=True, slots=True)
class SearchGroup:
    """Every hit of one kind.

    The kind is carried once, on the group, rather than repeated on each
    hit: it is a property of where the results came from, and stamping it
    onto every row would invite a caller to mix kinds into one flat list
    — where the ranks are not comparable.
    """

    kind: SearchKind
    matches: tuple[SearchMatch, ...]
    #: True when the kind had more rows than the caller's limit. Computed
    #: by over-fetching one row, not by a second `COUNT(*)` — a typeahead
    #: firing two queries per kind per keystroke is a self-inflicted load
    #: problem, and the exact overflow count is not worth showing anyway.
    has_more: bool


@dataclass(frozen=True, slots=True)
class SearchResults:
    #: Echoed back so a client rendering out-of-order responses can tell
    #: which keystroke a payload belongs to and drop stale ones.
    query: str
    groups: tuple[SearchGroup, ...]
