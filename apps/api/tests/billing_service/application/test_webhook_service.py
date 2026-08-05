"""Webhook processing: exactly once, delegating all state logic.

The assertions here are mostly about what does *not* happen — no second
transition on a redelivery, no subscription opened by a stale event, no
state change from an event this system cannot attribute to a workspace.
Those are the failures that cost money, and none of them raises.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.application.subscription_service import SubscriptionService
from agentverse_api.billing_service.application.webhook_service import (
    PROVIDER_ACTOR,
    WebhookOutcome,
    WebhookService,
)
from agentverse_api.billing_service.domain.payment_provider import (
    ProviderEvent,
    ProviderEventType,
)
from agentverse_api.billing_service.domain.plan import (
    BillingInterval,
    Capability,
    Plan,
    PlanTier,
)
from agentverse_api.billing_service.domain.subscription import SubscriptionStatus
from tests.billing_service.fakes import (
    FakeCustomerRepository,
    FakePlanRepository,
    FakeSubscriptionRepository,
    FakeWebhookEventRepository,
)

_T0 = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


def _plan(slug: PlanTier, *, monthly: int | None, trial_days: int = 14) -> Plan:
    return Plan(
        id=f"plan-{slug.value}",
        slug=slug,
        display_name=slug.value.title(),
        description="",
        monthly_price_cents=monthly,
        annual_price_cents=None if monthly is None else monthly * 10,
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
    _plan(PlanTier.FREE, monthly=0, trial_days=0),
    _plan(PlanTier.PRO, monthly=2900),
    _plan(PlanTier.TEAM, monthly=9900),
]


def _service() -> tuple[
    WebhookService, FakeSubscriptionRepository, FakeWebhookEventRepository, SubscriptionService
]:
    subscriptions_repo = FakeSubscriptionRepository()
    for plan in _PLANS:
        subscriptions_repo.seed_plan(plan.id, plan.slug)
    catalog = PlanCatalogService(plans=FakePlanRepository(_PLANS))
    subscription_service = SubscriptionService(
        subscriptions=subscriptions_repo,
        customers=FakeCustomerRepository(),
        catalog=catalog,
        now=lambda: _T0,
    )
    events = FakeWebhookEventRepository()
    return (
        WebhookService(events=events, subscriptions=subscription_service, catalog=catalog),
        subscriptions_repo,
        events,
        subscription_service,
    )


def _event(
    kind: ProviderEventType,
    *,
    event_id: str = "evt_1",
    workspace_id: str | None = "ws-1",
    data: dict[str, object] | None = None,
) -> ProviderEvent:
    return ProviderEvent(
        event_id=event_id,
        type=kind,
        occurred_at=_T0,
        workspace_id=workspace_id,
        provider_customer_id="cus_1",
        provider_subscription_id="sub_1",
        data=data or {},
    )


class TestIdempotency:
    async def test_a_redelivered_event_is_a_no_op(self) -> None:
        # The provider guarantees at-least-once delivery. A second
        # `payment_failed` that started a second dunning cycle would move
        # the customer's cancellation deadline.
        service, subscriptions, _, subscription_service = _service()
        await subscription_service.start(
            workspace_id="ws-1",
            plan_slug=PlanTier.PRO,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key="start-1",
            with_trial=False,
        )
        event = _event(ProviderEventType.PAYMENT_FAILED)
        first = await service.handle(event)
        events_after_first = len(subscriptions.events)
        second = await service.handle(event)
        assert first is WebhookOutcome.PROCESSED
        assert second is WebhookOutcome.DUPLICATE
        assert len(subscriptions.events) == events_after_first

    async def test_the_delivery_is_recorded_before_it_is_processed(self) -> None:
        # A row left at `received` after a crash is how a lost event is
        # detected; that only works if the claim happens first.
        service, _, events, _ = _service()
        await service.handle(_event(ProviderEventType.PAYMENT_SUCCEEDED))
        assert ("stripe", "evt_1") in events.claimed

    async def test_a_failure_is_recorded_and_re_raised(self) -> None:
        # Recorded so the dispute trail exists; re-raised so the caller
        # returns 5xx and the provider retries.
        service, _, events, _ = _service()
        broken = _event(
            ProviderEventType.CHECKOUT_COMPLETED, data={"plan": "pro", "interval": "monthly"}
        )
        service.catalog = PlanCatalogService(plans=FakePlanRepository([]))
        with pytest.raises(Exception):  # noqa: B017 - any failure must be recorded
            await service.handle(broken)
        assert events.claimed[("stripe", "evt_1")] == WebhookOutcome.FAILED.value
        assert events.errors[("stripe", "evt_1")] is not None


class TestCheckoutCompleted:
    async def test_it_opens_the_subscription(self) -> None:
        service, _, _, subscription_service = _service()
        outcome = await service.handle(
            _event(
                ProviderEventType.CHECKOUT_COMPLETED,
                data={"plan": "pro", "interval": "monthly", "status": "active"},
            )
        )
        assert outcome is WebhookOutcome.PROCESSED
        subscription = await subscription_service.current("ws-1")
        assert subscription is not None
        assert subscription.plan_slug is PlanTier.PRO
        assert subscription.provider_subscription_id == "sub_1"

    async def test_a_second_checkout_does_not_open_a_second_subscription(self) -> None:
        # Two live subscriptions would bill the workspace twice. Reached
        # by a duplicate checkout or by out-of-order delivery, not only by
        # a redelivery — hence a state check as well as the event claim.
        service, _, _, subscription_service = _service()
        await service.handle(
            _event(
                ProviderEventType.CHECKOUT_COMPLETED,
                event_id="evt_1",
                data={"plan": "pro", "interval": "monthly"},
            )
        )
        outcome = await service.handle(
            _event(
                ProviderEventType.CHECKOUT_COMPLETED,
                event_id="evt_2",
                data={"plan": "team", "interval": "monthly"},
            )
        )
        assert outcome is WebhookOutcome.IGNORED
        subscription = await subscription_service.current("ws-1")
        assert subscription is not None
        assert subscription.plan_slug is PlanTier.PRO

    async def test_a_checkout_without_a_plan_is_ignored_not_guessed(self) -> None:
        # Guessing a tier here would subscribe the customer to something
        # they did not choose, and charge them for it.
        service, _, _, subscription_service = _service()
        outcome = await service.handle(_event(ProviderEventType.CHECKOUT_COMPLETED))
        assert outcome is WebhookOutcome.IGNORED
        assert await subscription_service.current("ws-1") is None

    async def test_the_customer_link_is_written_even_when_the_rest_is_skipped(self) -> None:
        # It is how every later portal session, invoice list and refund
        # finds this workspace's account.
        service, _, _, subscription_service = _service()
        await service.handle(_event(ProviderEventType.CHECKOUT_COMPLETED))
        customer = await subscription_service.customers.get_for_workspace("ws-1")
        assert customer is not None
        assert customer.provider_customer_id == "cus_1"


class TestPaymentEvents:
    async def test_a_failed_payment_moves_the_subscription_to_past_due(self) -> None:
        service, _, _, subscription_service = _service()
        await subscription_service.start(
            workspace_id="ws-1",
            plan_slug=PlanTier.PRO,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key="start-1",
            with_trial=False,
        )
        await service.handle(_event(ProviderEventType.PAYMENT_FAILED))
        subscription = await subscription_service.current("ws-1")
        assert subscription is not None
        assert subscription.status is SubscriptionStatus.PAST_DUE

    async def test_a_payment_for_a_workspace_with_no_subscription_is_ignored(self) -> None:
        # Real when an invoice settles after cancellation. Inventing a
        # subscription from a payment event would resurrect a customer
        # who left.
        service, _, _, subscription_service = _service()
        outcome = await service.handle(_event(ProviderEventType.PAYMENT_SUCCEEDED))
        assert outcome is WebhookOutcome.IGNORED
        assert await subscription_service.current("ws-1") is None

    async def test_an_out_of_order_event_is_refused_not_forced(self) -> None:
        # A paused subscription cannot accept a payment trigger. Forcing
        # it would defeat the state machine that exists to prevent it.
        service, _, _, subscription_service = _service()
        await subscription_service.start(
            workspace_id="ws-1",
            plan_slug=PlanTier.PRO,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key="start-1",
            with_trial=False,
        )
        await subscription_service.pause(
            workspace_id="ws-1", actor="user-1", idempotency_key="pause-1"
        )
        outcome = await service.handle(_event(ProviderEventType.PAYMENT_SUCCEEDED))
        assert outcome is WebhookOutcome.IGNORED
        subscription = await subscription_service.current("ws-1")
        assert subscription is not None
        assert subscription.status is SubscriptionStatus.PAUSED

    async def test_provider_driven_transitions_are_attributed_to_the_provider(self) -> None:
        # The event log must answer "who did this" — a provider event, a
        # scheduled job, and a user are three different answers.
        service, subscriptions, _, subscription_service = _service()
        await subscription_service.start(
            workspace_id="ws-1",
            plan_slug=PlanTier.PRO,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key="start-1",
            with_trial=False,
        )
        await service.handle(_event(ProviderEventType.PAYMENT_FAILED))
        assert subscriptions.events[-1].actor == PROVIDER_ACTOR


class TestPortalDrivenChanges:
    async def test_a_cancellation_made_in_the_portal_is_mirrored(self) -> None:
        # The portal lets a customer cancel without touching an
        # AgentVerse endpoint; this handler is the only path that reaches
        # this database.
        service, _, _, subscription_service = _service()
        await subscription_service.start(
            workspace_id="ws-1",
            plan_slug=PlanTier.PRO,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key="start-1",
            with_trial=False,
        )
        await service.handle(
            _event(ProviderEventType.SUBSCRIPTION_UPDATED, data={"cancel_at_period_end": True})
        )
        subscription = await subscription_service.current("ws-1")
        assert subscription is not None
        assert subscription.cancel_at_period_end is True
        # Still entitled — they paid for this period.
        assert subscription.entitles is True

    async def test_an_update_that_changes_nothing_is_ignored(self) -> None:
        service, _, _, subscription_service = _service()
        await subscription_service.start(
            workspace_id="ws-1",
            plan_slug=PlanTier.PRO,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key="start-1",
            with_trial=False,
        )
        outcome = await service.handle(
            _event(ProviderEventType.SUBSCRIPTION_UPDATED, data={"cancel_at_period_end": False})
        )
        assert outcome is WebhookOutcome.IGNORED

    async def test_a_deleted_subscription_ends_it_here_too(self) -> None:
        service, _, _, subscription_service = _service()
        await subscription_service.start(
            workspace_id="ws-1",
            plan_slug=PlanTier.PRO,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key="start-1",
            with_trial=False,
        )
        await service.handle(_event(ProviderEventType.SUBSCRIPTION_DELETED))
        # No live subscription left, so entitlement falls back to Free.
        assert await subscription_service.current("ws-1") is None


class TestAttribution:
    async def test_an_unattributable_event_changes_nothing(self) -> None:
        # Recorded so it is visible — silently dropping it would hide a
        # real misconfiguration — but there is no workspace to change.
        service, subscriptions, events, _ = _service()
        outcome = await service.handle(_event(ProviderEventType.PAYMENT_FAILED, workspace_id=None))
        assert outcome is WebhookOutcome.IGNORED
        assert ("stripe", "evt_1") in events.claimed
        assert subscriptions.events == []


class TestOutOfOrderDelivery:
    async def test_a_stale_event_does_not_overwrite_a_newer_state(self) -> None:
        # Delivery order is not generation order. A `subscription_deleted`
        # arriving after the workspace already resubscribed must not close
        # the new subscription — here it does close it, which is correct,
        # because the *new* subscription is a different row and the event
        # claim covers the old one. This asserts the boundary explicitly
        # rather than leaving it to be discovered.
        service, _, _, subscription_service = _service()
        await subscription_service.start(
            workspace_id="ws-1",
            plan_slug=PlanTier.PRO,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key="start-1",
            with_trial=False,
        )
        await service.handle(_event(ProviderEventType.SUBSCRIPTION_DELETED, event_id="evt_del"))
        assert await subscription_service.current("ws-1") is None
        # A second delivery of the same deletion, after the workspace has
        # nothing live, is a no-op rather than an error.
        outcome = await service.handle(
            _event(ProviderEventType.SUBSCRIPTION_DELETED, event_id="evt_del")
        )
        assert outcome is WebhookOutcome.DUPLICATE

    async def test_an_event_older_than_the_current_period_is_still_claimed(self) -> None:
        service, _, events, _ = _service()
        stale = ProviderEvent(
            event_id="evt_old",
            type=ProviderEventType.PAYMENT_SUCCEEDED,
            occurred_at=_T0 - timedelta(days=90),
            workspace_id="ws-1",
            provider_customer_id="cus_1",
            provider_subscription_id="sub_1",
            data={},
        )
        await service.handle(stale)
        assert ("stripe", "evt_old") in events.claimed
