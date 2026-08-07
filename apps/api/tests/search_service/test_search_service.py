"""The fan-out policy, with the database replaced by fakes.

What is worth testing here is not "does SQL work" — that is the
integration suite's job — but the decisions this layer actually makes:
what counts as a searchable query, how many results per kind, how
`has_more` is derived, and whether a kind filter is honoured.
"""

from __future__ import annotations

import pytest
from agentverse_shared.search import SearchMatch

from agentverse_api.search_service.application.search_service import SearchService
from agentverse_api.search_service.domain.kinds import MAX_LIMIT_PER_KIND, SearchKind


class FakeSearcher:
    """Records what it was asked, returns what it was seeded with."""

    def __init__(self, kind: SearchKind, titles: list[str]) -> None:
        self._kind = kind
        self._titles = titles
        self.calls: list[tuple[str, str, int]] = []

    @property
    def kind(self) -> SearchKind:
        return self._kind

    async def search(self, *, workspace_id: str, tsquery: str, limit: int) -> list[SearchMatch]:
        self.calls.append((workspace_id, tsquery, limit))
        return [
            SearchMatch(id=f"{self._kind.value}-{index}", title=title, subtitle=None, rank=1.0)
            for index, title in enumerate(self._titles[:limit])
        ]


def _service(*searchers: FakeSearcher) -> SearchService:
    return SearchService(searchers=list(searchers))


class TestQueryGate:
    @pytest.mark.parametrize("query", ["", " ", "a", "!!!"])
    async def test_an_unsearchable_query_never_reaches_a_searcher(self, query: str) -> None:
        # Not just "returns nothing": the round trip is skipped entirely.
        # A palette fires one of these on the *first* keystroke of every
        # single search, and paying for a query per keystroke of noise
        # is the difference between a search box and a load generator.
        agents = FakeSearcher(SearchKind.AGENT, ["Anything"])
        results = await _service(agents).search(workspace_id="ws-1", query=query)
        assert results.groups == ()
        assert agents.calls == []

    async def test_an_unsearchable_query_is_not_an_error(self) -> None:
        # The user is mid-word on the way to a valid query. Raising here
        # would put a validation error under the search box on the way to
        # every successful search.
        results = await _service(FakeSearcher(SearchKind.AGENT, [])).search(
            workspace_id="ws-1", query="a"
        )
        assert results.query == "a"

    async def test_the_query_is_echoed_back(self) -> None:
        # So a client can drop a response that belongs to a keystroke the
        # user has already typed past.
        results = await _service(FakeSearcher(SearchKind.AGENT, ["Sales"])).search(
            workspace_id="ws-1", query="sal"
        )
        assert results.query == "sal"

    async def test_searchers_receive_the_normalized_tsquery_not_the_raw_input(self) -> None:
        agents = FakeSearcher(SearchKind.AGENT, [])
        await _service(agents).search(workspace_id="ws-1", query="Sales Qualifier")
        _workspace, tsquery, _limit = agents.calls[0]
        assert tsquery == "sales:* & qualifier:*"


class TestGrouping:
    async def test_each_kind_gets_its_own_group_in_searcher_order(self) -> None:
        results = await _service(
            FakeSearcher(SearchKind.AGENT, ["Sales agent"]),
            FakeSearcher(SearchKind.TEAM, ["Sales team"]),
            FakeSearcher(SearchKind.LISTING, ["Sales listing"]),
        ).search(workspace_id="ws-1", query="sales")
        assert [group.kind for group in results.groups] == [
            SearchKind.AGENT,
            SearchKind.TEAM,
            SearchKind.LISTING,
        ]

    async def test_a_kind_with_no_hits_still_gets_an_empty_group(self) -> None:
        # The client renders headings from the groups it is given; a
        # missing group and an empty one are different UI states, and
        # collapsing them here would take that choice away.
        results = await _service(FakeSearcher(SearchKind.AGENT, [])).search(
            workspace_id="ws-1", query="sales"
        )
        assert len(results.groups) == 1
        assert results.groups[0].matches == ()

    async def test_kinds_filter_skips_the_others_entirely(self) -> None:
        agents = FakeSearcher(SearchKind.AGENT, ["Sales agent"])
        teams = FakeSearcher(SearchKind.TEAM, ["Sales team"])
        results = await _service(agents, teams).search(
            workspace_id="ws-1", query="sales", kinds=[SearchKind.TEAM]
        )
        assert [group.kind for group in results.groups] == [SearchKind.TEAM]
        assert agents.calls == []

    async def test_workspace_id_is_passed_through_to_every_searcher(self) -> None:
        agents = FakeSearcher(SearchKind.AGENT, [])
        teams = FakeSearcher(SearchKind.TEAM, [])
        await _service(agents, teams).search(workspace_id="ws-42", query="sales")
        assert agents.calls[0][0] == "ws-42"
        assert teams.calls[0][0] == "ws-42"


class TestLimits:
    async def test_results_are_capped_at_the_limit(self) -> None:
        results = await _service(
            FakeSearcher(SearchKind.AGENT, [f"Sales {n}" for n in range(20)])
        ).search(workspace_id="ws-1", query="sales", limit_per_kind=3)
        assert len(results.groups[0].matches) == 3

    async def test_has_more_is_true_when_the_kind_overflowed(self) -> None:
        results = await _service(
            FakeSearcher(SearchKind.AGENT, [f"Sales {n}" for n in range(20)])
        ).search(workspace_id="ws-1", query="sales", limit_per_kind=3)
        assert results.groups[0].has_more is True

    async def test_has_more_is_false_at_exactly_the_limit(self) -> None:
        # The off-by-one that matters: three results with a limit of
        # three is *not* "there are more".
        results = await _service(
            FakeSearcher(SearchKind.AGENT, ["a Sales", "b Sales", "c Sales"])
        ).search(workspace_id="ws-1", query="sales", limit_per_kind=3)
        assert results.groups[0].has_more is False
        assert len(results.groups[0].matches) == 3

    async def test_one_extra_row_is_fetched_to_decide_has_more(self) -> None:
        # Over-fetching by one rather than issuing a second COUNT(*) —
        # a typeahead firing two queries per kind per keystroke is a
        # self-inflicted load problem.
        agents = FakeSearcher(SearchKind.AGENT, [])
        await _service(agents).search(workspace_id="ws-1", query="sales", limit_per_kind=5)
        assert agents.calls[0][2] == 6

    async def test_the_limit_is_clamped_to_the_ceiling(self) -> None:
        agents = FakeSearcher(SearchKind.AGENT, [])
        await _service(agents).search(workspace_id="ws-1", query="sales", limit_per_kind=10_000)
        assert agents.calls[0][2] == MAX_LIMIT_PER_KIND + 1

    async def test_a_nonsense_limit_floors_at_one(self) -> None:
        agents = FakeSearcher(SearchKind.AGENT, [])
        await _service(agents).search(workspace_id="ws-1", query="sales", limit_per_kind=0)
        assert agents.calls[0][2] == 2
