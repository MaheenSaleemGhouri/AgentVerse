"""The port every searchable context implements."""

from __future__ import annotations

from typing import Protocol

from agentverse_shared.search import SearchMatch

from agentverse_api.search_service.domain.kinds import SearchKind


class KindSearcher(Protocol):
    """One entity kind, searchable.

    `tsquery` arrives already built — by `to_prefix_tsquery`, once, in
    the application service. Handing each searcher the raw user string
    instead would mean four chances to normalize it differently, and one
    chance to pass it to `to_tsquery` unsanitized.
    """

    @property
    def kind(self) -> SearchKind: ...

    async def search(self, *, workspace_id: str, tsquery: str, limit: int) -> list[SearchMatch]: ...
