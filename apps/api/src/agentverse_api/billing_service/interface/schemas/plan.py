"""Response schemas for the plan catalog.

Money crosses this boundary as integer cents in a field whose name says
so (`monthly_price_cents`), never as a pre-formatted "$29.00" string.
Formatting is the client's job and depends on the viewer's locale;
sending a formatted string would bake one locale into the contract and
lose the exact value at the same time.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agentverse_api.billing_service.domain.plan import (
    BillingInterval,
    Plan,
    PlanTier,
    annual_saving_percent,
)


class OverageRateResponse(BaseModel):
    """Published overage pricing for one metered dimension.

    Both fields are needed to state the rate honestly: "300 cents" alone
    is meaningless without "per 1,000 runs".
    """

    dimension: str
    billing_increment: int
    price_cents_per_increment: int


class PlanResponse(BaseModel):
    id: str
    slug: PlanTier
    display_name: str
    description: str
    #: `None` means the tier is quoted, not published — the client must
    #: render "Contact sales", not a zero.
    monthly_price_cents: int | None
    annual_price_cents: int | None
    #: Percent saved by paying annually, or `None` when there is nothing
    #: to compare (free or custom-priced). Computed server-side so the
    #: pricing page and any future email or invoice quote the same
    #: number rather than each deriving its own.
    annual_saving_percent: int | None
    currency: str
    trial_days: int
    sort_order: int
    #: `null` in either map means unlimited on that dimension.
    resource_limits: dict[str, int | None]
    metered_allowances: dict[str, int | None]
    capabilities: list[str]
    overage_rates: list[OverageRateResponse]


class PlanListResponse(BaseModel):
    data: list[PlanResponse]
    #: Echoed so a client that cached the catalog can tell which interval
    #: the prices it holds were being displayed for.
    intervals: list[BillingInterval] = Field(
        default_factory=lambda: [BillingInterval.MONTHLY, BillingInterval.ANNUAL]
    )


def to_plan_response(plan: Plan) -> PlanResponse:
    return PlanResponse(
        id=plan.id,
        slug=plan.slug,
        display_name=plan.display_name,
        description=plan.description,
        monthly_price_cents=plan.monthly_price_cents,
        annual_price_cents=plan.annual_price_cents,
        annual_saving_percent=annual_saving_percent(plan),
        currency=plan.currency,
        trial_days=plan.trial_days,
        sort_order=plan.sort_order,
        resource_limits={key.value: value for key, value in plan.resource_limits.items()},
        metered_allowances={key.value: value for key, value in plan.metered_allowances.items()},
        # Sorted so the response is byte-stable across requests: the
        # domain holds a frozenset, whose iteration order is not
        # guaranteed, and an unstable list breaks HTTP caching and makes
        # contract snapshots flap for no reason.
        capabilities=sorted(capability.value for capability in plan.capabilities),
        overage_rates=[
            OverageRateResponse(
                dimension=rate.dimension.value,
                billing_increment=rate.billing_increment,
                price_cents_per_increment=rate.price_cents_per_increment,
            )
            for _, rate in sorted(plan.overage_rates.items(), key=lambda item: item[0].value)
        ],
    )
