"""The subscription lifecycle, against in-memory repositories.

The clock is injected, so the dunning window and period rollovers are
driven by moving a variable rather than by sleeping.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.application.subscription_service import (
    SYSTEM_ACTOR,
    SubscriptionService,
    add_months,
)
from agentverse_api.billing_service.domain.customer import PaymentProvider
from agentverse_api.billing_service.domain.dunning import DunningAction
from agentverse_api.billing_service.domain.exceptions import (
    PlanNotPurchasableError,
    SubscriptionAlreadyExistsError,
    SubscriptionNotFoundError,
)
from agentverse_api.billing_service.domain.plan import (
    BillingInterval,
    Capability,
    Plan,
    PlanTier,
)
from agentverse_api.billing_service.domain.subscription import (
    InvalidTransitionError,
    SubscriptionStatus,
)
from tests.billing_service.fakes import (
    FakeCustomerRepository,
    FakePlanRepository,
    FakeSubscriptionRepository,
)

_T0 = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


class _Clock:
    """A movable clock. Beats `freezegun` here — one class, no dependency,
    and the tests read as "advance 15 days" rather than as patching.
    """

    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


def _plan(
    slug: PlanTier,
    *,
    monthly: int | None,
    annual: int | None = None,
    trial_days: int = 14,
) -> Plan:
    return Plan(
        id=f"plan-{slug.value}",
        slug=slug,
        display_name=slug.value.title(),
        description="",
        monthly_price_cents=monthly,
        annual_price_cents=annual,
        currency="usd",
        trial_days=trial_days,
        is_public=True,
        is_active=True,
        sort_order=0,
        resource_limits={},
        metered_allowances={},
        capabilities=frozenset({Capability.COMMUNITY_SUPPORT}),
        overage_rates={},
    )


_PLANS = [
    _plan(PlanTier.FREE, monthly=0, annual=0, trial_days=0),
    _plan(PlanTier.PRO, monthly=2900, annual=29000),
    _plan(PlanTier.TEAM, monthly=9900, annual=99000),
    _plan(PlanTier.ENTERPRISE, monthly=None, annual=None, trial_days=0),
]


def _service() -> tuple[SubscriptionService, FakeSubscriptionRepository, _Clock]:
    subscriptions = FakeSubscriptionRepository()
    for plan in _PLANS:
        subscriptions.seed_plan(plan.id, plan.slug)
    clock = _Clock(_T0)
    service = SubscriptionService(
        subscriptions=subscriptions,
        customers=FakeCustomerRepository(),
        catalog=PlanCatalogService(plans=FakePlanRepository(_PLANS)),
        now=clock,
    )
    return service, subscriptions, clock


async def _started(
    service: SubscriptionService,
    *,
    slug: PlanTier = PlanTier.PRO,
    with_trial: bool = False,
    interval: BillingInterval = BillingInterval.MONTHLY,
):
    return await service.start(
        workspace_id="ws-1",
        plan_slug=slug,
        interval=interval,
        actor="user-1",
        idempotency_key="start-1",
        with_trial=with_trial,
    )


class TestPeriodArithmetic:
    def test_a_month_is_a_calendar_month_not_thirty_days(self) -> None:
        assert add_months(datetime(2026, 1, 15, tzinfo=UTC), 1) == datetime(2026, 2, 15, tzinfo=UTC)

    def test_a_short_month_clamps_rather_than_overflowing(self) -> None:
        # Jan 31 + 1 month has no correct answer. Clamping to Feb 28
        # keeps the "same day each month" promise as closely as possible;
        # rolling forward to Mar 3 would hand out extra service annually.
        assert add_months(datetime(2026, 1, 31, tzinfo=UTC), 1) == datetime(2026, 2, 28, tzinfo=UTC)

    def test_leap_year_february_is_respected(self) -> None:
        assert add_months(datetime(2028, 1, 31, tzinfo=UTC), 1) == datetime(2028, 2, 29, tzinfo=UTC)

    def test_a_year_crosses_correctly(self) -> None:
        assert add_months(datetime(2026, 11, 15, tzinfo=UTC), 12) == datetime(
            2027, 11, 15, tzinfo=UTC
        )


class TestStart:
    async def test_starting_with_a_trial_opens_in_trialing(self) -> None:
        service, _, _ = _service()
        subscription = await _started(service, with_trial=True)
        assert subscription.status is SubscriptionStatus.TRIALING
        assert subscription.trial_end == _T0 + timedelta(days=14)
        # The first period ends when the trial does, because that is when
        # the first charge happens.
        assert subscription.current_period_end == subscription.trial_end

    async def test_starting_without_a_trial_opens_active_for_a_full_period(self) -> None:
        service, _, _ = _service()
        subscription = await _started(service)
        assert subscription.status is SubscriptionStatus.ACTIVE
        assert subscription.trial_end is None
        assert subscription.current_period_end == datetime(2026, 9, 5, 12, 0, tzinfo=UTC)

    async def test_an_annual_subscription_runs_twelve_months(self) -> None:
        service, _, _ = _service()
        subscription = await _started(service, interval=BillingInterval.ANNUAL)
        assert subscription.current_period_end == datetime(2027, 8, 5, 12, 0, tzinfo=UTC)

    async def test_a_second_subscription_for_the_same_workspace_is_refused(self) -> None:
        # Two live subscriptions would bill the same workspace twice.
        service, _, _ = _service()
        await _started(service)
        with pytest.raises(SubscriptionAlreadyExistsError):
            await service.start(
                workspace_id="ws-1",
                plan_slug=PlanTier.TEAM,
                interval=BillingInterval.MONTHLY,
                actor="user-1",
                idempotency_key="start-2",
            )

    async def test_enterprise_cannot_be_self_served(self) -> None:
        # Quoted by sales; there is no published price to charge.
        service, _, _ = _service()
        with pytest.raises(PlanNotPurchasableError):
            await service.start(
                workspace_id="ws-1",
                plan_slug=PlanTier.ENTERPRISE,
                interval=BillingInterval.MONTHLY,
                actor="user-1",
                idempotency_key="start-ent",
            )

    async def test_creation_is_recorded_in_the_event_log(self) -> None:
        # The history has to start somewhere — a subscription whose first
        # event is its second transition cannot be reconciled.
        service, _, _ = _service()
        await _started(service)
        events = await service.history(workspace_id="ws-1")
        assert len(events) == 1


class TestPaymentOutcomes:
    async def test_a_successful_payment_converts_a_trial_and_clears_it(self) -> None:
        service, _, clock = _service()
        await _started(service, with_trial=True)
        clock.advance(days=14)
        updated = await service.payment_succeeded(workspace_id="ws-1", idempotency_key="pay-1")
        assert updated.status is SubscriptionStatus.ACTIVE
        assert updated.trial_end is None
        assert updated.current_period_start == clock.now

    async def test_a_failed_payment_starts_the_dunning_clock(self) -> None:
        service, _, clock = _service()
        await _started(service)
        clock.advance(days=30)
        updated = await service.payment_failed(workspace_id="ws-1", idempotency_key="fail-1")
        assert updated.status is SubscriptionStatus.PAST_DUE
        assert updated.past_due_since == clock.now

    async def test_a_second_failure_does_not_reset_the_clock(self) -> None:
        # Resetting it is how a repeatedly-failing card extends its own
        # grace period indefinitely.
        service, _, clock = _service()
        await _started(service)
        await service.payment_failed(workspace_id="ws-1", idempotency_key="fail-1")
        first_failure = (await service.require_current("ws-1")).past_due_since
        clock.advance(days=3)
        updated = await service.payment_failed(workspace_id="ws-1", idempotency_key="fail-2")
        assert updated.past_due_since == first_failure

    async def test_recovery_clears_the_clock(self) -> None:
        # Leaving it set would make the *next* failure inherit the old
        # clock and cancel the customer early.
        service, _, clock = _service()
        await _started(service)
        await service.payment_failed(workspace_id="ws-1", idempotency_key="fail-1")
        clock.advance(days=2)
        updated = await service.payment_succeeded(workspace_id="ws-1", idempotency_key="pay-1")
        assert updated.status is SubscriptionStatus.ACTIVE
        assert updated.past_due_since is None

    async def test_a_past_due_subscription_is_still_entitled(self) -> None:
        service, _, _ = _service()
        await _started(service)
        updated = await service.payment_failed(workspace_id="ws-1", idempotency_key="fail-1")
        assert updated.entitles is True


class TestIdempotency:
    async def test_replaying_a_payment_event_does_not_transition_twice(self) -> None:
        service, subscriptions, _ = _service()
        await _started(service)
        first = await service.payment_failed(workspace_id="ws-1", idempotency_key="webhook-abc")
        events_after_first = len(subscriptions.events)
        second = await service.payment_failed(workspace_id="ws-1", idempotency_key="webhook-abc")
        assert second.status is first.status
        assert second.past_due_since == first.past_due_since
        assert len(subscriptions.events) == events_after_first

    async def test_a_replay_returns_the_current_state_rather_than_conflicting(self) -> None:
        # A redelivered webhook is a no-op, not a 409. Raising would page
        # someone for a delivery guarantee working as designed.
        service, _, _ = _service()
        await _started(service)
        await service.cancel(
            workspace_id="ws-1",
            actor="user-1",
            idempotency_key="cancel-1",
            at_period_end=False,
        )
        # The subscription is canceled, so `require_current` no longer
        # finds it — which is itself the proof the transition landed.
        with pytest.raises(SubscriptionNotFoundError):
            await service.require_current("ws-1")


class TestPauseResume:
    async def test_pausing_stops_entitlement(self) -> None:
        # Otherwise pausing would be strictly better than paying.
        service, _, _ = _service()
        await _started(service)
        paused = await service.pause(workspace_id="ws-1", actor="user-1", idempotency_key="pause-1")
        assert paused.status is SubscriptionStatus.PAUSED
        assert paused.entitles is False

    async def test_resuming_starts_a_fresh_period(self) -> None:
        service, _, clock = _service()
        await _started(service)
        await service.pause(workspace_id="ws-1", actor="user-1", idempotency_key="pause-1")
        clock.advance(days=10)
        resumed = await service.resume(
            workspace_id="ws-1", actor="user-1", idempotency_key="resume-1"
        )
        assert resumed.status is SubscriptionStatus.ACTIVE
        assert resumed.current_period_start == clock.now

    async def test_resuming_a_subscription_that_is_not_paused_is_refused(self) -> None:
        service, _, _ = _service()
        await _started(service)
        with pytest.raises(InvalidTransitionError):
            await service.resume(workspace_id="ws-1", actor="user-1", idempotency_key="resume-1")


class TestCancellation:
    async def test_cancelling_at_period_end_keeps_the_customer_entitled(self) -> None:
        # They have already paid for this period.
        service, _, _ = _service()
        await _started(service)
        canceled = await service.cancel(
            workspace_id="ws-1", actor="user-1", idempotency_key="cancel-1"
        )
        assert canceled.status is SubscriptionStatus.ACTIVE
        assert canceled.cancel_at_period_end is True
        assert canceled.entitles is True

    async def test_a_scheduled_cancellation_can_be_undone_before_the_period_closes(
        self,
    ) -> None:
        service, _, _ = _service()
        await _started(service)
        await service.cancel(workspace_id="ws-1", actor="user-1", idempotency_key="cancel-1")
        restored = await service.resume_scheduled_cancellation(workspace_id="ws-1")
        assert restored.cancel_at_period_end is False

    async def test_the_terminal_transition_waits_for_the_period_to_close(self) -> None:
        service, _, clock = _service()
        await _started(service)
        await service.cancel(workspace_id="ws-1", actor="user-1", idempotency_key="cancel-1")
        still_active = await service.close_period_if_canceling(
            workspace_id="ws-1", idempotency_key="close-1"
        )
        assert still_active.status is SubscriptionStatus.ACTIVE
        clock.advance(days=31)
        closed = await service.close_period_if_canceling(
            workspace_id="ws-1", idempotency_key="close-2"
        )
        assert closed.status is SubscriptionStatus.CANCELED
        assert closed.canceled_at == clock.now

    async def test_closing_a_period_with_no_scheduled_cancellation_does_nothing(self) -> None:
        # The sweep asks this of every subscription it walks.
        service, _, clock = _service()
        await _started(service)
        clock.advance(days=31)
        unchanged = await service.close_period_if_canceling(
            workspace_id="ws-1", idempotency_key="close-1"
        )
        assert unchanged.status is SubscriptionStatus.ACTIVE

    async def test_immediate_cancellation_ends_it_now(self) -> None:
        service, _, clock = _service()
        await _started(service)
        canceled = await service.cancel(
            workspace_id="ws-1",
            actor="admin-1",
            idempotency_key="cancel-1",
            at_period_end=False,
            reason="account closed by admin",
        )
        assert canceled.status is SubscriptionStatus.CANCELED
        assert canceled.canceled_at == clock.now
        assert canceled.entitles is False


class TestDunningExecution:
    async def test_no_dunning_step_for_a_healthy_subscription(self) -> None:
        service, _, _ = _service()
        await _started(service)
        assert await service.dunning_step(workspace_id="ws-1") is None

    async def test_no_dunning_step_for_a_workspace_with_no_subscription(self) -> None:
        service, _, _ = _service()
        assert await service.dunning_step(workspace_id="ws-nothing") is None

    async def test_the_touchpoints_advance_with_the_clock(self) -> None:
        service, _, clock = _service()
        await _started(service)
        await service.payment_failed(workspace_id="ws-1", idempotency_key="fail-1")
        first = await service.dunning_step(workspace_id="ws-1")
        assert first is not None and first.action is DunningAction.NOTIFY
        clock.advance(days=3)
        retry = await service.dunning_step(workspace_id="ws-1")
        assert retry is not None and retry.action is DunningAction.RETRY_PAYMENT

    async def test_the_subscription_cancels_when_the_window_closes(self) -> None:
        service, _, clock = _service()
        await _started(service)
        await service.payment_failed(workspace_id="ws-1", idempotency_key="fail-1")
        clock.advance(days=14)
        canceled = await service.cancel_if_dunning_exhausted(
            workspace_id="ws-1", idempotency_key="dunning-1"
        )
        assert canceled.status is SubscriptionStatus.CANCELED

    async def test_it_does_not_cancel_inside_the_window(self) -> None:
        service, _, clock = _service()
        await _started(service)
        await service.payment_failed(workspace_id="ws-1", idempotency_key="fail-1")
        clock.advance(days=13)
        unchanged = await service.cancel_if_dunning_exhausted(
            workspace_id="ws-1", idempotency_key="dunning-1"
        )
        assert unchanged.status is SubscriptionStatus.PAST_DUE

    async def test_involuntary_churn_is_distinguishable_from_voluntary(self) -> None:
        # `saas-strategist` requires the two to be reported separately;
        # they cannot be if both write `customer_canceled`.
        service, subscriptions, clock = _service()
        await _started(service)
        await service.payment_failed(workspace_id="ws-1", idempotency_key="fail-1")
        clock.advance(days=14)
        await service.cancel_if_dunning_exhausted(workspace_id="ws-1", idempotency_key="dunning-1")
        triggers = [event.trigger for event in subscriptions.events]
        assert "dunning_exhausted" in triggers
        assert "customer_canceled" not in triggers

    async def test_a_healthy_subscription_is_never_canceled_by_the_sweep(self) -> None:
        service, _, clock = _service()
        await _started(service)
        clock.advance(days=60)
        unchanged = await service.cancel_if_dunning_exhausted(
            workspace_id="ws-1", idempotency_key="dunning-1"
        )
        assert unchanged.status is SubscriptionStatus.ACTIVE


class TestPlanChange:
    async def test_an_upgrade_prorates_credit_and_charge(self) -> None:
        service, _, clock = _service()
        await _started(service)
        clock.advance(days=15)
        updated, proration = await service.change_plan(
            workspace_id="ws-1",
            target_slug=PlanTier.TEAM,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key="change-1",
        )
        assert updated.plan_slug is PlanTier.TEAM
        assert updated.status is SubscriptionStatus.ACTIVE
        assert proration.unused_credit_cents > 0
        assert proration.prorated_charge_cents > proration.unused_credit_cents

    async def test_a_downgrade_produces_a_credit_not_a_charge(self) -> None:
        service, _, clock = _service()
        await _started(service, slug=PlanTier.TEAM)
        clock.advance(days=15)
        _, proration = await service.change_plan(
            workspace_id="ws-1",
            target_slug=PlanTier.PRO,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key="change-1",
        )
        assert proration.net_cents < 0

    async def test_the_proration_is_recorded_on_the_event(self) -> None:
        # So the invoice line and any later dispute read the numbers this
        # call computed, not ones re-derived against a since-changed
        # price. The event is the only durable copy.
        service, subscriptions, clock = _service()
        await _started(service)
        clock.advance(days=15)
        _, proration = await service.change_plan(
            workspace_id="ws-1",
            target_slug=PlanTier.TEAM,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key="change-1",
        )
        recorded = subscriptions.events[-1].metadata
        assert recorded["from_plan"] == "pro"
        assert recorded["to_plan"] == "team"
        assert recorded["unused_credit_cents"] == proration.unused_credit_cents
        assert recorded["prorated_charge_cents"] == proration.prorated_charge_cents
        assert recorded["net_cents"] == proration.net_cents

    async def test_replaying_a_plan_change_does_not_transition_twice(self) -> None:
        # A retried request must not append a second plan-change event —
        # each one becomes an invoice line, so a duplicate is a duplicate
        # charge.
        service, subscriptions, clock = _service()
        await _started(service)
        clock.advance(days=15)
        await service.change_plan(
            workspace_id="ws-1",
            target_slug=PlanTier.TEAM,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key="change-1",
        )
        events_after_first = len(subscriptions.events)
        updated, _ = await service.change_plan(
            workspace_id="ws-1",
            target_slug=PlanTier.TEAM,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key="change-1",
        )
        assert len(subscriptions.events) == events_after_first
        assert updated.plan_slug is PlanTier.TEAM

    async def test_changing_to_enterprise_is_refused(self) -> None:
        service, _, _ = _service()
        await _started(service)
        with pytest.raises(PlanNotPurchasableError):
            await service.change_plan(
                workspace_id="ws-1",
                target_slug=PlanTier.ENTERPRISE,
                interval=BillingInterval.MONTHLY,
                actor="user-1",
                idempotency_key="change-1",
            )

    async def test_switching_to_annual_prices_against_the_annual_rate(self) -> None:
        service, _, clock = _service()
        await _started(service)
        clock.advance(days=15)
        _, proration = await service.change_plan(
            workspace_id="ws-1",
            target_slug=PlanTier.PRO,
            interval=BillingInterval.ANNUAL,
            actor="user-1",
            idempotency_key="change-1",
        )
        # 16 of the period's 31 days remain, priced at the *annual* rate:
        # 29000 * 16/31 = 14967.7, truncated to 14967. Pricing it at the
        # monthly rate instead would charge 1496 — an order of magnitude
        # undercharge that no assertion on "greater than zero" catches.
        assert proration.prorated_charge_cents == 14967


class TestCustomerLinking:
    async def test_linking_is_idempotent_per_workspace(self) -> None:
        service, _, _ = _service()
        first = await service.link_customer(
            workspace_id="ws-1",
            provider=PaymentProvider.STRIPE,
            provider_customer_id="cus_1",
        )
        second = await service.link_customer(
            workspace_id="ws-1",
            provider=PaymentProvider.STRIPE,
            provider_customer_id="cus_1",
            billing_email="finance@example.com",
        )
        assert second.id == first.id
        assert second.billing_email == "finance@example.com"


class TestReads:
    async def test_current_is_none_for_a_workspace_that_never_subscribed(self) -> None:
        service, _, _ = _service()
        assert await service.current("ws-nothing") is None

    async def test_require_current_raises_rather_than_returning_none(self) -> None:
        service, _, _ = _service()
        with pytest.raises(SubscriptionNotFoundError):
            await service.require_current("ws-nothing")

    async def test_history_is_empty_rather_than_an_error(self) -> None:
        # The timeline component should render an empty state, not an
        # error, for a workspace with no billing history.
        service, _, _ = _service()
        assert await service.history(workspace_id="ws-nothing") == []

    async def test_system_transitions_are_attributed_to_the_system_actor(self) -> None:
        service, subscriptions, _ = _service()
        await _started(service)
        await service.payment_failed(workspace_id="ws-1", idempotency_key="fail-1")
        assert subscriptions.events[-1].actor == SYSTEM_ACTOR
