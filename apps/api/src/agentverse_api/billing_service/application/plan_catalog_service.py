"""Reading the plan catalog.

Thin by design. The catalog is data, not behaviour — the interesting
logic lives in `domain/plan.py`'s arithmetic and in the entitlement
resolution next door. What this service owns is the one rule that is not
a pure function: **a workspace with no subscription is on Free**, and
Free must therefore always be resolvable.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_api.billing_service.domain.exceptions import (
    CatalogIncompleteError,
    PlanNotFoundError,
)
from agentverse_api.billing_service.domain.plan import Plan, PlanTier
from agentverse_api.billing_service.domain.ports import PlanRepository


@dataclass(slots=True)
class PlanCatalogService:
    plans: PlanRepository

    async def list_plans(self, *, include_private: bool = False) -> list[Plan]:
        """The published catalog.

        `include_private` is off by default so the common path cannot
        accidentally leak a withdrawn or grandfathered plan onto the
        pricing page — the caller has to ask for it explicitly.
        """
        return await self.plans.list_active(public_only=not include_private)

    async def get_plan(self, slug: PlanTier) -> Plan:
        plan = await self.plans.get_by_slug(slug)
        if plan is None:
            raise PlanNotFoundError(slug.value)
        return plan

    async def default_plan(self) -> Plan:
        """The plan a workspace is on when it has no subscription.

        Raises rather than falling back to hardcoded limits. A hardcoded
        fallback would be a second, invisible copy of the pricing config
        that only appears when the real one is missing — which is
        precisely when nobody is watching (Rule 3).
        """
        plan = await self.plans.get_by_slug(PlanTier.FREE)
        if plan is None:
            raise CatalogIncompleteError(PlanTier.FREE)
        return plan
