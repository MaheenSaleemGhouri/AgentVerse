"""`/api/v1/plans` — the published plan catalog.

**Unauthenticated, deliberately.** Every other route in this service
resolves an identity first, so the exception needs a reason rather than
a convention:

- It returns published pricing and nothing else. There is no
  `workspace_id` in the request, no tenant row in the response, and no
  way to ask for a plan that is not marked public — `public_only` is
  hardcoded, not a query parameter, so the withdrawn and grandfathered
  rows the catalog also holds cannot be reached from here at all.
- The public pricing page has no session by definition. Requiring one
  would mean the marketing page and the in-product plan picker read
  their prices from two different places, which is the exact
  single-source violation the `plans` table exists to prevent (Rule 3).

`apps/api` is not internet-routable (see the trust-boundary diagram in
`docs/security/security-architecture.md`); this endpoint is reachable
only through `apps/web`, which is where public traffic is rate-limited.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.domain.exceptions import PlanNotFoundError
from agentverse_api.billing_service.domain.plan import PlanTier
from agentverse_api.billing_service.interface.dependencies.services import (
    get_plan_catalog_service,
)
from agentverse_api.billing_service.interface.schemas.plan import (
    PlanListResponse,
    PlanResponse,
    to_plan_response,
)

router = APIRouter(prefix="/api/v1/plans", tags=["billing-plans"])


@router.get("", response_model=PlanListResponse)
async def list_plans_route(
    service: PlanCatalogService = Depends(get_plan_catalog_service),
) -> PlanListResponse:
    plans = await service.list_plans()
    return PlanListResponse(data=[to_plan_response(plan) for plan in plans])


@router.get("/{slug}", response_model=PlanResponse)
async def get_plan_route(
    slug: PlanTier,
    service: PlanCatalogService = Depends(get_plan_catalog_service),
) -> PlanResponse:
    """A single tier by slug.

    `slug` is typed as `PlanTier`, so an unknown value is a 422 from
    FastAPI's own validation rather than reaching the database. A slug
    that is valid but deactivated is a 404 — a real state, since a
    client can hold a slug from a pricing page cached before the plan
    was withdrawn.
    """
    try:
        plan = await service.get_plan(slug)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if not plan.is_public:
        # Reachable by guessing a slug. Answered as 404 rather than 403
        # so this endpoint cannot be used to probe which private tiers
        # exist — the same existence-hiding rule tenant resources follow
        # (Rule 11).
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return to_plan_response(plan)
