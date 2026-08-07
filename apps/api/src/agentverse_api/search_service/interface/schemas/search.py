"""Wire schemas for search."""

from __future__ import annotations

from pydantic import BaseModel

from agentverse_api.search_service.domain.kinds import SearchKind
from agentverse_api.search_service.domain.results import SearchGroup, SearchResults


class SearchHitOut(BaseModel):
    #: For agents, knowledge bases and teams this is the row id. For
    #: listings it is the slug, because that is how the catalog is
    #: addressed — a client builds its link from `kind` + `id` and needs
    #: no per-kind exception beyond that.
    id: str
    title: str
    subtitle: str | None = None


class SearchGroupOut(BaseModel):
    kind: SearchKind
    hits: list[SearchHitOut]
    has_more: bool


class SearchResultsOut(BaseModel):
    query: str
    groups: list[SearchGroupOut]

    @classmethod
    def from_domain(cls, results: SearchResults) -> SearchResultsOut:
        return cls(
            query=results.query,
            groups=[_group_out(group) for group in results.groups],
        )


def _group_out(group: SearchGroup) -> SearchGroupOut:
    return SearchGroupOut(
        kind=group.kind,
        hits=[
            # `rank` is deliberately not on the wire. It is a
            # `ts_rank_cd` float that only orders rows *within* one kind;
            # exposing it invites a client to sort across kinds by it,
            # which would be meaningless. The order of `hits` is the
            # ranking, and that is all a client needs.
            SearchHitOut(id=match.id, title=match.title, subtitle=match.subtitle)
            for match in group.matches
        ],
        has_more=group.has_more,
    )
