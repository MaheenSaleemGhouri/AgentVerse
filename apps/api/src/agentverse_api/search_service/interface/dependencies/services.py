"""Composition root for search.

Every port search depends on is bound here, and every one of them is a
repository belonging to another context. That is what makes the boundary
checkable: this file is the complete list of what search touches, and it
contains no table names.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.infrastructure.db import get_db_session
from agentverse_api.marketplace_service.infrastructure.repositories import SqlListingRepository
from agentverse_api.orchestration_service.infrastructure.knowledge_repository import (
    SqlKnowledgeRepository,
)
from agentverse_api.orchestration_service.infrastructure.repositories import SqlAgentRepository
from agentverse_api.orchestration_service.infrastructure.team_repository import SqlTeamRepository
from agentverse_api.search_service.application.search_service import SearchService
from agentverse_api.search_service.infrastructure.searchers import (
    AgentSearcher,
    KnowledgeBaseSearcher,
    ListingSearcher,
    TeamSearcher,
)


def get_search_service(session: AsyncSession = Depends(get_db_session)) -> SearchService:
    """Order matters: it is the order the groups come back in, and the
    order the palette renders them. Agents first because that is what a
    workspace has most of and searches for most often; the catalog last
    because it is the only group that is not the user's own work.
    """
    return SearchService(
        searchers=[
            AgentSearcher(SqlAgentRepository(session)),
            KnowledgeBaseSearcher(SqlKnowledgeRepository(session)),
            TeamSearcher(SqlTeamRepository(session)),
            ListingSearcher(SqlListingRepository(session)),
        ]
    )
