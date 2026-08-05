"""Catalog reads, against an in-memory `PlanRepository`."""

from __future__ import annotations

import pytest

from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.domain.exceptions import (
    CatalogIncompleteError,
    PlanNotFoundError,
)
from agentverse_api.billing_service.domain.plan import Plan, PlanTier


def _plan(slug: PlanTier, *, is_public: bool = True, sort_order: int = 0) -> Plan:
    return Plan(
        id=f"plan-{slug.value}",
        slug=slug,
        display_name=slug.value.title(),
        description="",
        monthly_price_cents=0,
        annual_price_cents=0,
        currency="usd",
        trial_days=0,
        is_public=is_public,
        is_active=True,
        sort_order=sort_order,
        resource_limits={},
        metered_allowances={},
        capabilities=frozenset(),
        overage_rates={},
    )


class FakePlanRepository:
    """Mirrors `SqlPlanRepository`'s filtering, including the
    `public_only` predicate — a fake that skipped it would let a test
    pass while the real query hid the row.
    """

    def __init__(self, plans: list[Plan]) -> None:
        self._plans = plans

    async def list_active(self, *, public_only: bool) -> list[Plan]:
        return [
            plan for plan in self._plans if plan.is_active and (plan.is_public or not public_only)
        ]

    async def get_by_slug(self, slug: PlanTier) -> Plan | None:
        for plan in self._plans:
            if plan.slug == slug and plan.is_active:
                return plan
        return None


class TestListPlans:
    async def test_hides_private_plans_by_default(self) -> None:
        # A grandfathered plan must still resolve for the workspaces on
        # it, but publishing it would offer a price the product no longer
        # sells.
        service = PlanCatalogService(
            plans=FakePlanRepository([_plan(PlanTier.FREE), _plan(PlanTier.PRO, is_public=False)])
        )
        slugs = [plan.slug for plan in await service.list_plans()]
        assert slugs == [PlanTier.FREE]

    async def test_include_private_must_be_asked_for_explicitly(self) -> None:
        service = PlanCatalogService(
            plans=FakePlanRepository([_plan(PlanTier.FREE), _plan(PlanTier.PRO, is_public=False)])
        )
        slugs = {plan.slug for plan in await service.list_plans(include_private=True)}
        assert slugs == {PlanTier.FREE, PlanTier.PRO}


class TestGetPlan:
    async def test_missing_plan_raises_rather_than_returning_none(self) -> None:
        # A `None` return would push the "what does this mean" decision
        # onto every call site; a plan slug that no longer resolves is a
        # 404, and that is decided once.
        service = PlanCatalogService(plans=FakePlanRepository([_plan(PlanTier.FREE)]))
        with pytest.raises(PlanNotFoundError):
            await service.get_plan(PlanTier.ENTERPRISE)


class TestDefaultPlan:
    async def test_resolves_free_for_a_workspace_with_no_subscription(self) -> None:
        service = PlanCatalogService(plans=FakePlanRepository([_plan(PlanTier.FREE)]))
        assert (await service.default_plan()).slug is PlanTier.FREE

    async def test_missing_free_row_fails_loudly_instead_of_falling_back(self) -> None:
        # The failure this prevents is the worst kind: a hardcoded
        # fallback would be a second, invisible copy of the pricing
        # config that only takes effect when the real one is missing —
        # exactly when nobody is watching.
        service = PlanCatalogService(plans=FakePlanRepository([_plan(PlanTier.PRO)]))
        with pytest.raises(CatalogIncompleteError):
            await service.default_plan()
