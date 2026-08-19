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
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_embedding_provider,
)


def get_marketplace_service(
    session: AsyncSession = Depends(get_db_session),
) -> MarketplaceService:
    # `SqlListingRepository` implements both `ListingRepository` and
    # `ListingSearchPort` — one table, one adapter, structurally
    # satisfying two Protocols rather than two objects that would need
    # to agree on the same session. Reused via the shared embedding
    # provider (Rule 16): the same adapter apps/worker uses for
    # knowledge-base ingestion, so a listing and a KB chunk embed into
    # the same vector space.
    listings = SqlListingRepository(session)
    return MarketplaceService(
        listings=listings,
        versions=SqlListingVersionRepository(session),
        reviews=SqlReviewRepository(session),
        categories=SqlCategoryRepository(session),
        search=listings,
        embedder=get_embedding_provider(),
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
