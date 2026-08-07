"""Fan a query out across every searchable kind and group the results."""

from __future__ import annotations

from collections.abc import Sequence

from agentverse_shared.search import is_searchable, to_prefix_tsquery

from agentverse_api.search_service.domain.kinds import (
    DEFAULT_LIMIT_PER_KIND,
    MAX_LIMIT_PER_KIND,
    SearchKind,
)
from agentverse_api.search_service.domain.ports import KindSearcher
from agentverse_api.search_service.domain.results import SearchGroup, SearchResults


class SearchService:
    """Cross-kind search.

    Holds no SQL of its own: every query is issued by the context that
    owns the table, through a `KindSearcher`. What lives here is the
    policy — what counts as a searchable query, how many results per
    kind, and in what order the groups come back.
    """

    def __init__(self, searchers: Sequence[KindSearcher]) -> None:
        self._searchers = tuple(searchers)

    async def search(
        self,
        *,
        workspace_id: str,
        query: str,
        kinds: Sequence[SearchKind] | None = None,
        limit_per_kind: int = DEFAULT_LIMIT_PER_KIND,
    ) -> SearchResults:
        """Search every requested kind.

        A query with too little signal returns empty groups rather than
        raising. This backs a typeahead: the user is *mid-word* on their
        way to a valid query, and answering a keystroke with a validation
        error would put a red banner under the search box on the way to
        every successful search.
        """
        if not is_searchable(query):
            return SearchResults(query=query, groups=())

        tsquery = to_prefix_tsquery(query)
        if tsquery is None:  # pragma: no cover - `is_searchable` already implies this
            return SearchResults(query=query, groups=())

        limit = max(1, min(limit_per_kind, MAX_LIMIT_PER_KIND))
        wanted = None if kinds is None else set(kinds)

        groups: list[SearchGroup] = []
        for searcher in self._searchers:
            if wanted is not None and searcher.kind not in wanted:
                continue
            # Sequentially, not `asyncio.gather`. Every searcher shares
            # one `AsyncSession`, and SQLAlchemy's async session is not
            # safe for concurrent use — gathering here would raise
            # `InvalidRequestError`/`MissingGreenlet` under exactly the
            # load that makes it look worth parallelizing.
            matches = await searcher.search(
                workspace_id=workspace_id, tsquery=tsquery, limit=limit + 1
            )
            groups.append(
                SearchGroup(
                    kind=searcher.kind,
                    matches=tuple(matches[:limit]),
                    has_more=len(matches) > limit,
                )
            )

        return SearchResults(query=query, groups=tuple(groups))
