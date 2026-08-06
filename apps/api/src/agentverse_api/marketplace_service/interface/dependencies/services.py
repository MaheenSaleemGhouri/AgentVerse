"""Composition root for the marketplace context."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.infrastructure.db import get_db_session
from agentverse_api.marketplace_service.application.install_service import (
    InstallService,
    ModerationService,
)
from agentverse_api.marketplace_service.application.marketplace_service import (
    MarketplaceService,
)
from agentverse_api.marketplace_service.infrastructure.agent_importer import (
    OrchestrationAgentImporter,
)
from agentverse_api.marketplace_service.infrastructure.repositories import (
    SqlCategoryRepository,
    SqlInstallRepository,
    SqlListingRepository,
    SqlListingVersionRepository,
    SqlReviewRepository,
)
from agentverse_api.orchestration_service.infrastructure.repositories import (
    SqlAgentRepository,
)


def get_marketplace_service(
    session: AsyncSession = Depends(get_db_session),
) -> MarketplaceService:
    return MarketplaceService(
        listings=SqlListingRepository(session),
        versions=SqlListingVersionRepository(session),
        reviews=SqlReviewRepository(session),
        categories=SqlCategoryRepository(session),
    )


def get_install_service(session: AsyncSession = Depends(get_db_session)) -> InstallService:
    """Binds the one port that crosses a context boundary.

    `AgentImporter` is satisfied here by an adapter over orchestration's
    own use case — the marketplace never writes `agents`/`agent_versions`
    itself (Rule 5). This is the single place the two contexts meet, and
    keeping that in the composition root is what makes it checkable.
    """
    return InstallService(
        listings=SqlListingRepository(session),
        versions=SqlListingVersionRepository(session),
        installs=SqlInstallRepository(session),
        agents=OrchestrationAgentImporter(SqlAgentRepository(session)),
    )


def get_moderation_service(
    session: AsyncSession = Depends(get_db_session),
) -> ModerationService:
    return ModerationService(listings=SqlListingRepository(session))
