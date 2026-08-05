"""Turning a finalized period into invoice lines.

Kept apart from `usage_service.py` deliberately — `billing-expert`
requires aggregation ("what was used") and invoice generation ("what that
costs") to be distinct, individually testable steps. Collapsing them
would make it impossible to test that a total is right without also
asserting a price, and vice versa.

**Invoicing reads finalized rollups, never the raw events.** A period
that has not been closed has no invoice, and an issued invoice cannot
change because a late event arrived afterwards. The live usage panel
reads the events; the invoice reads the frozen totals. Those are
different questions and it matters that they cannot be confused.

**This produces a draft, not a charge.** The payment provider issues and
collects. What this computes is what the customer is *shown*, and the
number the provider's own invoice is checked against — two independent
computations that agree is a reconciliation, one nobody can check is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.application.usage_service import UsageService
from agentverse_api.billing_service.domain.invoice import DraftInvoice, build_draft_invoice
from agentverse_api.billing_service.domain.plan import BillingInterval
from agentverse_api.billing_service.domain.subscription import Subscription


class PeriodNotFinalizedError(Exception):
    """The period's totals have not been frozen. Maps to HTTP 409.

    Refused rather than computed from live events: an invoice built from
    a period still accepting usage would change between being shown and
    being paid, and a customer who screenshots one number and is charged
    another has a legitimate complaint.
    """

    def __init__(self, workspace_id: str, period_start: datetime) -> None:
        self.workspace_id = workspace_id
        self.period_start = period_start
        super().__init__(
            f"Billing period starting {period_start.isoformat()} for workspace "
            f"{workspace_id!r} has not been finalized; no invoice can be issued for it."
        )


@dataclass(slots=True)
class InvoicingService:
    usage: UsageService
    catalog: PlanCatalogService

    async def _plan_and_interval(
        self, workspace_id: str
    ) -> tuple[Subscription | None, BillingInterval]:
        subscription = await self.usage.subscriptions.current(workspace_id)
        interval = subscription.interval if subscription is not None else BillingInterval.MONTHLY
        return subscription, interval

    async def preview_current_period(self, workspace_id: str) -> DraftInvoice:
        """What this period would cost if it closed right now.

        Built from *live* usage, which is the one place that is correct:
        this is explicitly a forecast the customer is looking at mid-
        period, and labelling it a preview is what makes reading live
        events honest here rather than the mistake it would be in
        `issue_for_period`.

        `saas-strategist`'s no-surprise-billing rule in practice — the
        overage a customer will owe is visible before the invoice, not
        discovered on it.
        """
        subscription, interval = await self._plan_and_interval(workspace_id)
        plan = (
            await self.catalog.get_plan(subscription.plan_slug)
            if subscription is not None and subscription.entitles
            else await self.catalog.default_plan()
        )
        usage = await self.usage.current_period_usage(workspace_id)
        return build_draft_invoice(plan=plan, interval=interval, usage=usage)

    async def issue_for_period(self, *, workspace_id: str, period_start: datetime) -> DraftInvoice:
        """The real thing: built only from frozen totals.

        Raises if the period was never finalized. That refusal is the
        point — every other path in this service can be re-run safely,
        and this is the one that must not produce a number that later
        moves.
        """
        subscription, interval = await self._plan_and_interval(workspace_id)
        stored = await self.usage.usage.finalized_rollups(
            workspace_id=workspace_id, period_start=period_start
        )
        if stored is None:
            raise PeriodNotFinalizedError(workspace_id, period_start)
        plan = (
            await self.catalog.get_plan(subscription.plan_slug)
            if subscription is not None
            else await self.catalog.default_plan()
        )
        return build_draft_invoice(plan=plan, interval=interval, usage=stored)
