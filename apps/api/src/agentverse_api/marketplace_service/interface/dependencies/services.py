"""Composition root for the marketplace context."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.infrastructure.db import get_db_session
from agentverse_api.marketplace_service.application.marketplace_service import (
    MarketplaceService,
)
from agentverse_api.marketplace_service.infrastructure.repositories import (
    SqlCategoryRepository,
    SqlListingRepository,
    SqlListingVersionRepository,
    SqlReviewRepository,
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
