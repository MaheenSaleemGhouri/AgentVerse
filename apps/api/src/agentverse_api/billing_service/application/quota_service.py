"""Deciding whether a workspace may consume more of a metered dimension.

The one rule this exists to enforce: **a workspace at its limit is
stopped before the expensive work starts, server-side.** Checking in the
UI is not enforcement — a direct API call bypasses it — and checking
after the run is not enforcement either, because the provider cost has
already been paid.

**Whether exceeding is refused or billed is a property of the plan, not
of this code.** A dimension with an overage rate is one the customer has
agreed to pay for beyond the allowance, so passing the allowance is
allowed and produces an invoice line. A dimension without one is a hard
stop. That is what makes Free genuinely free: it carries no overage
rates at all, so a free workspace is refused at its limit and there is
no code path that can invoice it.

**There is deliberately no Redis fast-path yet.** A cached counter would
be an optimisation with a correctness cost (Rule 13: Redis is never the
source), and nothing here has been measured as slow — the check is one
indexed aggregate on `(workspace_id, occurred_at, dimension)`, issued
once per run submission, against work that then takes seconds. Adding a
cache before there is a number to justify it is the speculative
complexity Rule 10 forbids.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from agentverse_api.billing_service.application.entitlement_service import EntitlementService
from agentverse_api.billing_service.application.usage_service import UsageService
from agentverse_api.billing_service.domain.plan import MeteredDimension, remaining


@dataclass(frozen=True, slots=True)
class QuotaDecision:
    """Why a request was allowed or refused.

    Carries the numbers, not just a boolean, so the 429 body can tell the
    customer what they hit and by how much — "you have used 10,000 of
    10,000 agent runs" is actionable; "quota exceeded" is not.
    """

    dimension: MeteredDimension
    allowed: bool
    allowance: int | None
    used: int
    #: When the current billing period rolls over and the allowance
    #: resets. Becomes the `Retry-After` hint on a refusal — a customer
    #: refused with no reset time cannot tell a rate limit from an
    #: outage.
    resets_at: datetime
    #: `True` when the plan bills beyond the allowance rather than
    #: refusing. The request proceeds and produces an invoice line.
    billable_overage: bool

    @property
    def remaining(self) -> int | None:
        return remaining(limit=self.allowance, used=self.used)

    def retry_after_seconds(self, now: datetime) -> int:
        """Seconds until the allowance resets, floored at one.

        Takes `now` rather than reading a clock so the value is
        deterministic and the same in a test as in a response. Floored at
        one because `Retry-After: 0` tells a client to retry immediately
        into the same refusal.
        """
        return max(1, int((self.resets_at - now).total_seconds()))


class QuotaExceededError(Exception):
    """The workspace is at a hard limit. Maps to HTTP 429.

    429 rather than 402: the request is not refused because payment
    failed, it is refused because a rate has been exhausted and will
    reset. `retry_after` is what distinguishes it from an outage.
    """

    def __init__(self, decision: QuotaDecision) -> None:
        self.decision = decision
        super().__init__(
            f"Workspace has used {decision.used:,} of its "
            f"{decision.allowance:,} included {decision.dimension.value}"
            if decision.allowance is not None
            else f"Quota exceeded for {decision.dimension.value}"
        )


@dataclass(slots=True)
class QuotaService:
    entitlements: EntitlementService
    usage: UsageService

    async def check(
        self, *, workspace_id: str, dimension: MeteredDimension, requested: int = 1
    ) -> QuotaDecision:
        """Would consuming `requested` more units be allowed?

        `requested` defaults to 1 (one run, one call) but is a parameter
        because a bulk import legitimately consumes many at once, and
        admitting it one unit at a time would let it pass a check it
        collectively fails.
        """
        plan = await self.entitlements.plan_for(workspace_id)
        allowance = plan.metered_allowance(dimension)
        period_start, period_end = await self.usage.current_period_bounds(workspace_id)
        billable = dimension in plan.overage_rates

        if allowance is None:
            # Unlimited. No query needed — the answer cannot depend on
            # the count, and skipping the aggregate is the difference
            # between a free check and one per request for every
            # Enterprise workspace.
            return QuotaDecision(
                dimension=dimension,
                allowed=True,
                allowance=None,
                used=0,
                resets_at=period_end,
                billable_overage=billable,
            )

        usage = await self.usage.usage.usage_for_period(
            workspace_id=workspace_id, period_start=period_start, period_end=period_end
        )
        used = usage.quantity(dimension)
        # `>` not `>=`: a workspace at exactly its allowance has used all
        # of it, so one more unit takes it over. Comparing the *result*
        # of the request rather than the state before it is what makes a
        # bulk request of 500 units fail when only 3 remain.
        within = (used + requested) <= allowance
        return QuotaDecision(
            dimension=dimension,
            allowed=within or billable,
            allowance=allowance,
            used=used,
            resets_at=period_end,
            billable_overage=billable,
        )

    async def enforce(
        self, *, workspace_id: str, dimension: MeteredDimension, requested: int = 1
    ) -> QuotaDecision:
        """Check, and raise if refused. The call sites use this."""
        decision = await self.check(
            workspace_id=workspace_id, dimension=dimension, requested=requested
        )
        if not decision.allowed:
            raise QuotaExceededError(decision)
        return decision
