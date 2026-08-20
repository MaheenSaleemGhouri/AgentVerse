"""Capability-check dependency factory (docs/adr/0018), sibling to
`require_role.py` but resolving an entitlement question rather than
gating a request: `Depends(require_capability(Capability.X))` never
raises — it resolves to `True`/`False` so a route can *route* on a plan
capability (e.g. which worker queue stream to enqueue onto) rather than
refuse the request outright. `require_role` denies-by-default because a
permission ceiling is a security boundary; a capability check here is a
routing decision, and refusing an entire run because a billing-side
lookup hiccupped would trade a minor infrastructure question for a real
outage — so a lookup failure resolves to `False` ("not entitled"),
matching the same best-effort/fail-open shape `UsageService.
record_quietly` already uses for a similar reliability-over-strictness
boundary.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.get_current_workspace import (
    get_current_workspace,
)
from agentverse_api.billing_service.application.entitlement_service import EntitlementService
from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.domain.plan import Capability
from agentverse_api.billing_service.infrastructure.repositories import (
    SqlPlanRepository,
    SqlSubscriptionRepository,
    SqlWorkspaceUsageRepository,
)
from agentverse_api.infrastructure.db import get_db_session

logger = logging.getLogger(__name__)


def require_capability(
    capability: Capability,
) -> Callable[..., Coroutine[Any, Any, bool]]:
    """Dependency factory: `Depends(require_capability(Capability.PRIORITY_QUEUE))`."""

    async def _dependency(
        context: WorkspaceContext = Depends(get_current_workspace),
        session: AsyncSession = Depends(get_db_session),
    ) -> bool:
        entitlements = EntitlementService(
            catalog=PlanCatalogService(plans=SqlPlanRepository(session)),
            usage=SqlWorkspaceUsageRepository(session),
            subscriptions=SqlSubscriptionRepository(session),
        )
        try:
            return await entitlements.grants(
                workspace_id=context.workspace_id, capability=capability
            )
        except Exception:
            logger.exception(
                "capability_entitlement_lookup_failed",
                extra={"workspace_id": context.workspace_id, "capability": capability.value},
            )
            return False

    return _dependency
