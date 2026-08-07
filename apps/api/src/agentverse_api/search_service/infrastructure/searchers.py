"""Adapters binding `KindSearcher` to each owning context's repository.

Every class here is four lines of delegation, and that is the point: the
query, the index it uses and the tenant predicate all live in the context
that owns the table. If search ever needs a new kind, the work is a
`search_*` method on that entity's repository plus an adapter here —
never a join reaching across a context boundary.
"""

from __future__ import annotations

from agentverse_shared.search import SearchMatch

from agentverse_api.marketplace_service.domain.ports import ListingRepository
from agentverse_api.orchestration_service.domain.ports.agent_repository import AgentRepository
from agentverse_api.orchestration_service.domain.ports.knowledge_repository import (
    KnowledgeRepository,
)
from agentverse_api.orchestration_service.domain.ports.team_repository import TeamRepository
from agentverse_api.search_service.domain.kinds import SearchKind


class AgentSearcher:
    def __init__(self, agents: AgentRepository) -> None:
        self._agents = agents

    @property
    def kind(self) -> SearchKind:
        return SearchKind.AGENT

    async def search(self, *, workspace_id: str, tsquery: str, limit: int) -> list[SearchMatch]:
        return await self._agents.search_agents(
            workspace_id=workspace_id, tsquery=tsquery, limit=limit
        )


class KnowledgeBaseSearcher:
    def __init__(self, knowledge: KnowledgeRepository) -> None:
        self._knowledge = knowledge

    @property
    def kind(self) -> SearchKind:
        return SearchKind.KNOWLEDGE_BASE

    async def search(self, *, workspace_id: str, tsquery: str, limit: int) -> list[SearchMatch]:
        return await self._knowledge.search_knowledge_bases(
            workspace_id=workspace_id, tsquery=tsquery, limit=limit
        )


class TeamSearcher:
    def __init__(self, teams: TeamRepository) -> None:
        self._teams = teams

    @property
    def kind(self) -> SearchKind:
        return SearchKind.TEAM

    async def search(self, *, workspace_id: str, tsquery: str, limit: int) -> list[SearchMatch]:
        return await self._teams.search_teams(
            workspace_id=workspace_id, tsquery=tsquery, limit=limit
        )


class ListingSearcher:
    """The public catalog.

    Takes `workspace_id` and ignores it — deliberately, and this is the
    only searcher that does. A published listing is public (see
    `marketplace_service/domain/listing.py`), so scoping catalog results
    to the searcher's own workspace would hide every listing they could
    actually install. The parameter stays in the signature because the
    port is uniform; dropping it here would mean the fan-out had to know
    which searchers are tenant-scoped, which is exactly the knowledge
    this indirection exists to keep out of it.
    """

    def __init__(self, listings: ListingRepository) -> None:
        self._listings = listings

    @property
    def kind(self) -> SearchKind:
        return SearchKind.LISTING

    async def search(self, *, workspace_id: str, tsquery: str, limit: int) -> list[SearchMatch]:
        return await self._listings.search_published(tsquery=tsquery, limit=limit)
