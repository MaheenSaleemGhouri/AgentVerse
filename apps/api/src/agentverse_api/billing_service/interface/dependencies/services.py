"""Composition root for the billing context — routes depend on these
factories and never build a repository themselves (mirrors
`auth_service`'s `dependencies/services.py`).
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.billing_service.application.entitlement_service import EntitlementService
from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.application.subscription_service import SubscriptionService
from agentverse_api.billing_service.infrastructure.repositories import (
    SqlCustomerRepository,
    SqlPlanRepository,
    SqlSubscriptionRepository,
    SqlWorkspaceUsageRepository,
)
from agentverse_api.infrastructure.db import get_db_session


def get_plan_catalog_service(
    session: AsyncSession = Depends(get_db_session),
) -> PlanCatalogService:
    return PlanCatalogService(plans=SqlPlanRepository(session))


def get_entitlement_service(
    session: AsyncSession = Depends(get_db_session),
) -> EntitlementService:
    return EntitlementService(
        catalog=PlanCatalogService(plans=SqlPlanRepository(session)),
        usage=SqlWorkspaceUsageRepository(session),
        subscriptions=SqlSubscriptionRepository(session),
    )


def get_subscription_service(
    session: AsyncSession = Depends(get_db_session),
) -> SubscriptionService:
    return SubscriptionService(
        subscriptions=SqlSubscriptionRepository(session),
        customers=SqlCustomerRepository(session),
        catalog=PlanCatalogService(plans=SqlPlanRepository(session)),
    )
