"""Driving the subscription lifecycle.

Every method that changes state funnels through `_transition`, which does
three things in a fixed order: check whether this trigger has already
been applied (idempotency), ask the domain whether the transition is
legal, then write the new status and its event row together. Nothing
here sets a status directly, and there is no path that writes one
without the other.

**Every trigger is named, not inferred.** The service takes an explicit
`SubscriptionTrigger` and an `actor` from its caller. A payment outcome
arrives from the processor's verified webhook (M3); a pause or a cancel
arrives from an authenticated request; a dunning outcome arrives from the
sweep job. None of them is deduced from a client-supplied field, which is
`billing-expert`'s first operating principle.

**Period arithmetic is calendar-aware.** A monthly period advances by one
calendar month, not 30 days, because a customer billed on the 31st and a
customer billed on the 1st both expect their next invoice on the same day
of the following month. `relativedelta` is not a dependency here, so the
month arithmetic is written out — it is a dozen lines and one edge case
(short months), which is cheaper than a dependency and easier to test.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.domain import dunning
from agentverse_api.billing_service.domain.customer import BillingCustomer, PaymentProvider
from agentverse_api.billing_service.domain.exceptions import (
    PlanNotPurchasableError,
    SubscriptionAlreadyExistsError,
    SubscriptionNotFoundError,
)
from agentverse_api.billing_service.domain.plan import (
    BillingInterval,
    Plan,
    PlanTier,
    price_cents,
)
from agentverse_api.billing_service.domain.ports import (
    CustomerRepository,
    SubscriptionRepository,
)
from agentverse_api.billing_service.domain.proration import Proration, prorate
from agentverse_api.billing_service.domain.subscription import (
    Subscription,
    SubscriptionStatus,
    SubscriptionTrigger,
    apply,
)

#: Actor string for transitions with no human behind them.
SYSTEM_ACTOR = "system:billing"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def add_months(moment: datetime, months: int) -> datetime:
    """Same day-of-month, `months` later, clamped to the month's length.

    The clamp is the whole reason this exists: January 31 plus one month
    has no correct answer, and every billing system has to pick one.
    February 28/29 is the convention — moving *forward* to March 3 would
    silently give the customer three extra days of service every year,
    and moving to March 1 breaks the "same day each month" promise more
    visibly than clamping does.
    """
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def period_end(*, start: datetime, interval: BillingInterval) -> datetime:
    return add_months(start, 12 if interval is BillingInterval.ANNUAL else 1)


@dataclass(slots=True)
class SubscriptionService:
    subscriptions: SubscriptionRepository
    customers: CustomerRepository
    catalog: PlanCatalogService
    #: Injected so tests can drive the dunning clock and period rollovers
    #: without sleeping. Production passes the default.
    now: Callable[[], datetime] = field(default=_utc_now)

    # ---- reads -------------------------------------------------------

    async def current(self, workspace_id: str) -> Subscription | None:
        return await self.subscriptions.get_for_workspace(workspace_id)

    async def require_current(self, workspace_id: str) -> Subscription:
        subscription = await self.subscriptions.get_for_workspace(workspace_id)
        if subscription is None:
            raise SubscriptionNotFoundError(workspace_id)
        return subscription

    async def history(
        self, *, workspace_id: str, limit: int = 50
    ) -> list[tuple[str, str, str, str, datetime]]:
        subscription = await self.subscriptions.get_for_workspace(workspace_id)
        if subscription is None:
            return []
        return await self.subscriptions.list_events(subscription_id=subscription.id, limit=limit)

    # ---- the one write path ------------------------------------------

    async def _transition(
        self,
        *,
        subscription: Subscription,
        trigger: SubscriptionTrigger,
        idempotency_key: str,
        actor: str,
        reason: str | None = None,
        metadata: dict[str, object] | None = None,
        changes: dict[str, object] | None = None,
    ) -> Subscription:
        """Apply one trigger, exactly once.

        The idempotency check runs *before* the legality check on
        purpose. A redelivered webhook for a transition that already
        happened would fail the legality check too (the subscription has
        moved on), but it would fail as a 409 conflict — which reads as a
        real problem and would page someone — rather than as the no-op it
        actually is.
        """
        existing = await self.subscriptions.find_event_by_idempotency_key(idempotency_key)
        if existing is not None:
            replayed = await self.subscriptions.get_by_id(existing)
            if replayed is not None:
                return replayed
            # The event exists but its subscription does not. Only
            # reachable if the subscription was hard-deleted, which the
            # application never does; treating it as "already applied" is
            # still the safe answer, because re-applying would be a
            # second charge-affecting transition.
            return subscription
        to_status = apply(status=subscription.status, trigger=trigger)
        return await self.subscriptions.record_transition(
            subscription_id=subscription.id,
            trigger=trigger,
            from_status=subscription.status,
            to_status=to_status,
            idempotency_key=idempotency_key,
            actor=actor,
            reason=reason,
            metadata=metadata or {},
            changes=changes or {},
        )

    # ---- lifecycle ---------------------------------------------------

    async def start(
        self,
        *,
        workspace_id: str,
        plan_slug: PlanTier,
        interval: BillingInterval,
        actor: str,
        idempotency_key: str,
        with_trial: bool = True,
        provider_subscription_id: str | None = None,
    ) -> Subscription:
        """Open a subscription for a workspace that has none.

        Refuses rather than replacing an existing one: an upgrade from an
        existing subscription is `change_plan`, and quietly creating a
        second row here would leave two live subscriptions billing the
        same workspace.
        """
        if await self.subscriptions.get_for_workspace(workspace_id) is not None:
            raise SubscriptionAlreadyExistsError(workspace_id)
        plan = await self._purchasable_plan(plan_slug, interval)
        started = self.now()
        trial_days = plan.trial_days if with_trial else 0
        trial_end = started + timedelta(days=trial_days) if trial_days else None
        status = SubscriptionStatus.TRIALING if trial_end else SubscriptionStatus.ACTIVE
        # A trial's first period runs to the end of the trial, not a full
        # month past signup: the period boundary is when the first charge
        # happens, and those are the same moment.
        ends = trial_end or period_end(start=started, interval=interval)
        return await self.subscriptions.create(
            workspace_id=workspace_id,
            plan_id=plan.id,
            status=status,
            interval=interval,
            current_period_start=started,
            current_period_end=ends,
            trial_end=trial_end,
            provider_subscription_id=provider_subscription_id,
            idempotency_key=idempotency_key,
            actor=actor,
        )

    async def _purchasable_plan(self, slug: PlanTier, interval: BillingInterval) -> Plan:
        plan = await self.catalog.get_plan(slug)
        if plan.is_custom_priced:
            raise PlanNotPurchasableError(
                slug.value, "custom-priced tiers are quoted by sales, not self-served"
            )
        if price_cents(plan, interval) is None:
            raise PlanNotPurchasableError(slug.value, f"has no published {interval.value} price")
        return plan

    async def payment_succeeded(
        self,
        *,
        workspace_id: str,
        idempotency_key: str,
        actor: str = SYSTEM_ACTOR,
        reason: str | None = None,
    ) -> Subscription:
        """A verified successful charge: converts a trial, renews an
        active period, or recovers a past-due subscription.

        Recovery clears `past_due_since` — leaving it set would make the
        next failure inherit the *old* dunning clock and cancel the
        customer early.
        """
        subscription = await self.require_current(workspace_id)
        started = self.now()
        changes: dict[str, object] = {
            "current_period_start": started,
            "current_period_end": period_end(start=started, interval=subscription.interval),
            "past_due_since": None,
            # The trial is over the moment a real payment lands.
            "trial_end": None,
        }
        return await self._transition(
            subscription=subscription,
            trigger=SubscriptionTrigger.PAYMENT_SUCCEEDED,
            idempotency_key=idempotency_key,
            actor=actor,
            reason=reason,
            changes=changes,
        )

    async def payment_failed(
        self,
        *,
        workspace_id: str,
        idempotency_key: str,
        actor: str = SYSTEM_ACTOR,
        reason: str | None = None,
    ) -> Subscription:
        """A verified failed charge. Starts the dunning clock on the first
        failure and deliberately leaves it alone on subsequent ones — see
        `domain/dunning.py` for why resetting it is how subscriptions get
        stuck in `past_due` forever.
        """
        subscription = await self.require_current(workspace_id)
        changes: dict[str, object] = {}
        if subscription.past_due_since is None:
            changes["past_due_since"] = self.now()
        return await self._transition(
            subscription=subscription,
            trigger=SubscriptionTrigger.PAYMENT_FAILED,
            idempotency_key=idempotency_key,
            actor=actor,
            reason=reason,
            changes=changes,
        )

    async def pause(self, *, workspace_id: str, actor: str, idempotency_key: str) -> Subscription:
        subscription = await self.require_current(workspace_id)
        return await self._transition(
            subscription=subscription,
            trigger=SubscriptionTrigger.CUSTOMER_PAUSED,
            idempotency_key=idempotency_key,
            actor=actor,
            reason="paused by customer",
        )

    async def resume(self, *, workspace_id: str, actor: str, idempotency_key: str) -> Subscription:
        """Resume starts a fresh period from now.

        Not "restore the remaining days of the period they paused in":
        that would require tracking paused-time and crediting it, and the
        customer was not being charged while paused, so starting clean is
        both simpler and in their favor for anything under a full period.
        """
        subscription = await self.require_current(workspace_id)
        resumed = self.now()
        return await self._transition(
            subscription=subscription,
            trigger=SubscriptionTrigger.CUSTOMER_RESUMED,
            idempotency_key=idempotency_key,
            actor=actor,
            reason="resumed by customer",
            changes={
                "current_period_start": resumed,
                "current_period_end": period_end(start=resumed, interval=subscription.interval),
            },
        )

    async def cancel(
        self,
        *,
        workspace_id: str,
        actor: str,
        idempotency_key: str,
        at_period_end: bool = True,
        reason: str | None = None,
    ) -> Subscription:
        """Cancel now, or at the end of the paid period.

        `at_period_end` is the default because it is what the customer has
        already paid for. It sets a flag and returns a still-`ACTIVE`
        subscription — entitlement is unchanged until the period closes,
        and `close_period_if_canceling` performs the terminal transition.
        Immediate cancellation is available for the cases that need it
        (an admin closing an account, a fraud response), and it does not
        refund — a refund is a separate deliberate action (M3), never an
        automatic side effect.
        """
        subscription = await self.require_current(workspace_id)
        if at_period_end:
            return await self.subscriptions.set_cancel_at_period_end(
                subscription_id=subscription.id, cancel_at_period_end=True
            )
        return await self._transition(
            subscription=subscription,
            trigger=SubscriptionTrigger.CUSTOMER_CANCELED,
            idempotency_key=idempotency_key,
            actor=actor,
            reason=reason or "canceled by customer",
            changes={"canceled_at": self.now(), "cancel_at_period_end": False},
        )

    async def resume_scheduled_cancellation(self, *, workspace_id: str) -> Subscription:
        """Undo a scheduled cancellation while the period is still open.

        Not a state transition — the subscription never left `ACTIVE` —
        so it does not go through `_transition` and does not need an
        idempotency key. Setting the flag back twice is the same as
        setting it once.
        """
        subscription = await self.require_current(workspace_id)
        return await self.subscriptions.set_cancel_at_period_end(
            subscription_id=subscription.id, cancel_at_period_end=False
        )

    async def close_period_if_canceling(
        self, *, workspace_id: str, idempotency_key: str
    ) -> Subscription:
        """The end-of-period half of a scheduled cancellation.

        Run by the billing sweep. Doing nothing when the period has not
        closed or no cancellation is scheduled is correct, not an error:
        the sweep asks this of every subscription it walks.
        """
        subscription = await self.require_current(workspace_id)
        if not subscription.cancel_at_period_end:
            return subscription
        if self.now() < subscription.current_period_end:
            return subscription
        return await self._transition(
            subscription=subscription,
            trigger=SubscriptionTrigger.PERIOD_ENDED_AFTER_CANCEL,
            idempotency_key=idempotency_key,
            actor=SYSTEM_ACTOR,
            reason="scheduled cancellation reached the end of the paid period",
            changes={"canceled_at": self.now()},
        )

    # ---- plan changes ------------------------------------------------

    async def change_plan(
        self,
        *,
        workspace_id: str,
        target_slug: PlanTier,
        interval: BillingInterval,
        actor: str,
        idempotency_key: str,
    ) -> tuple[Subscription, Proration]:
        """Move to another plan mid-cycle, with the proration that implies.

        Returns the proration alongside the subscription rather than
        applying it: turning a credit and a charge into money movement is
        the payment provider's job (M3) and an invoice line's (M4). This
        method's contract is "the plan changed, and here is exactly what
        that is worth" — computed from stored timestamps, so recomputing
        it later reproduces the same cents.
        """
        subscription = await self.require_current(workspace_id)
        current_plan = await self.catalog.get_plan(subscription.plan_slug)
        target_plan = await self._purchasable_plan(target_slug, interval)
        old_price = price_cents(current_plan, subscription.interval) or 0
        new_price = price_cents(target_plan, interval) or 0
        proration = prorate(
            old_price_cents=old_price,
            new_price_cents=new_price,
            period_start=subscription.current_period_start,
            period_end=subscription.current_period_end,
            change_at=self.now(),
        )
        updated = await self._transition(
            subscription=subscription,
            trigger=SubscriptionTrigger.PLAN_CHANGED,
            idempotency_key=idempotency_key,
            actor=actor,
            reason=f"{subscription.plan_slug.value} -> {target_slug.value}",
            metadata={
                "from_plan": subscription.plan_slug.value,
                "to_plan": target_slug.value,
                "from_interval": subscription.interval.value,
                "to_interval": interval.value,
                # Stored on the event so the invoice line and any later
                # dispute read the same numbers this call computed,
                # rather than re-deriving them against a plan whose price
                # may have changed since.
                "unused_credit_cents": proration.unused_credit_cents,
                "prorated_charge_cents": proration.prorated_charge_cents,
                "net_cents": proration.net_cents,
            },
        )
        if updated.plan_id != target_plan.id or updated.interval is not interval:
            updated = await self.subscriptions.change_plan(
                subscription_id=updated.id, plan_id=target_plan.id, interval=interval
            )
        return updated, proration

    # ---- dunning -----------------------------------------------------

    async def dunning_step(self, *, workspace_id: str) -> dunning.DunningStep | None:
        """What the dunning runner should do for this workspace right now.

        `None` for anything not past due — including a healthy
        subscription and a workspace with none at all.
        """
        subscription = await self.subscriptions.get_for_workspace(workspace_id)
        if subscription is None or subscription.past_due_since is None:
            return None
        if subscription.status is not SubscriptionStatus.PAST_DUE:
            return None
        return dunning.due_step(first_failure_at=subscription.past_due_since, now=self.now())

    async def cancel_if_dunning_exhausted(
        self, *, workspace_id: str, idempotency_key: str
    ) -> Subscription:
        """Involuntary churn: the dunning window closed without recovery.

        Separated from voluntary cancellation by its own trigger so the
        two are distinguishable in the event log — `saas-strategist`
        requires voluntary and involuntary churn to be reported as
        separate problems, and they cannot be if both write
        `customer_canceled`.
        """
        subscription = await self.require_current(workspace_id)
        if subscription.status is not SubscriptionStatus.PAST_DUE:
            return subscription
        if subscription.past_due_since is None:
            return subscription
        if not dunning.is_exhausted(first_failure_at=subscription.past_due_since, now=self.now()):
            return subscription
        return await self._transition(
            subscription=subscription,
            trigger=SubscriptionTrigger.DUNNING_EXHAUSTED,
            idempotency_key=idempotency_key,
            actor=SYSTEM_ACTOR,
            reason=f"no successful payment within {dunning.DUNNING_WINDOW_DAYS} days",
            changes={"canceled_at": self.now()},
        )

    # ---- payment-processor identity ----------------------------------

    async def link_customer(
        self,
        *,
        workspace_id: str,
        provider: PaymentProvider,
        provider_customer_id: str,
        billing_email: str | None = None,
    ) -> BillingCustomer:
        return await self.customers.upsert(
            workspace_id=workspace_id,
            provider=provider,
            provider_customer_id=provider_customer_id,
            billing_email=billing_email,
        )
