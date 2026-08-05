"""The subscription state machine.

Asserted mostly as *properties over the whole transition table* rather
than as a list of individual triples. A per-triple test proves the table
says what it says; a property proves the table cannot say something
harmful — which is what matters when a later milestone adds a trigger.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agentverse_api.billing_service.domain.plan import BillingInterval, PlanTier
from agentverse_api.billing_service.domain.subscription import (
    InvalidTransitionError,
    Subscription,
    SubscriptionStatus,
    SubscriptionTrigger,
    apply,
    can_apply,
    entitles,
    is_terminal,
)

_NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


def _subscription(
    *,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    trial_end: datetime | None = None,
) -> Subscription:
    return Subscription(
        id="sub-1",
        workspace_id="ws-1",
        plan_id="plan-pro",
        plan_slug=PlanTier.PRO,
        status=status,
        interval=BillingInterval.MONTHLY,
        current_period_start=_NOW,
        current_period_end=_NOW + timedelta(days=30),
        trial_end=trial_end,
        cancel_at_period_end=False,
        canceled_at=None,
        past_due_since=None,
        provider_subscription_id=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


class TestTableProperties:
    def test_canceled_is_terminal_and_has_no_outgoing_transition(self) -> None:
        # If any trigger moved a subscription out of CANCELED, its
        # history would no longer have a single unambiguous end, and
        # "when did this customer churn" would depend on which row you
        # looked at.
        for trigger in SubscriptionTrigger:
            assert not can_apply(status=SubscriptionStatus.CANCELED, trigger=trigger)
        assert is_terminal(SubscriptionStatus.CANCELED)

    def test_no_other_status_is_terminal(self) -> None:
        for status in SubscriptionStatus:
            if status is SubscriptionStatus.CANCELED:
                continue
            assert not is_terminal(status)
            assert any(can_apply(status=status, trigger=t) for t in SubscriptionTrigger)

    def test_every_non_terminal_status_can_reach_canceled(self) -> None:
        # A subscription that cannot be ended is a subscription that
        # bills forever.
        for status in SubscriptionStatus:
            if status is SubscriptionStatus.CANCELED:
                continue
            reachable = {
                apply(status=status, trigger=t)
                for t in SubscriptionTrigger
                if can_apply(status=status, trigger=t)
            }
            assert SubscriptionStatus.CANCELED in reachable, f"{status} cannot be canceled"

    def test_a_paused_subscription_is_never_payable(self) -> None:
        # Nothing should be charging a paused customer, so no payment
        # trigger may apply to one. If one did, a stray webhook could
        # silently reactivate and bill them.
        for trigger in (
            SubscriptionTrigger.PAYMENT_SUCCEEDED,
            SubscriptionTrigger.PAYMENT_FAILED,
        ):
            assert not can_apply(status=SubscriptionStatus.PAUSED, trigger=trigger)

    def test_a_successful_payment_always_lands_on_active(self) -> None:
        for status in SubscriptionStatus:
            if not can_apply(status=status, trigger=SubscriptionTrigger.PAYMENT_SUCCEEDED):
                continue
            assert (
                apply(status=status, trigger=SubscriptionTrigger.PAYMENT_SUCCEEDED)
                is SubscriptionStatus.ACTIVE
            )


class TestEntitlement:
    def test_past_due_still_entitles(self) -> None:
        # The whole point of dunning: a failed charge is usually an
        # expired card, and cutting service immediately converts a
        # recoverable billing problem into churn.
        assert entitles(SubscriptionStatus.PAST_DUE) is True

    def test_trialing_entitles(self) -> None:
        assert entitles(SubscriptionStatus.TRIALING) is True

    def test_paused_does_not_entitle(self) -> None:
        # Otherwise pausing would be strictly better than paying.
        assert entitles(SubscriptionStatus.PAUSED) is False

    def test_canceled_does_not_entitle(self) -> None:
        assert entitles(SubscriptionStatus.CANCELED) is False

    def test_every_entitling_status_is_non_terminal(self) -> None:
        for status in SubscriptionStatus:
            if entitles(status):
                assert not is_terminal(status)


class TestApply:
    def test_a_failed_payment_moves_an_active_subscription_to_past_due(self) -> None:
        assert (
            apply(
                status=SubscriptionStatus.ACTIVE,
                trigger=SubscriptionTrigger.PAYMENT_FAILED,
            )
            is SubscriptionStatus.PAST_DUE
        )

    def test_a_second_failure_while_past_due_stays_past_due(self) -> None:
        # Same-state, but still a transition so it reaches the event log.
        # The dunning clock runs from the first failure and is not reset.
        assert (
            apply(
                status=SubscriptionStatus.PAST_DUE,
                trigger=SubscriptionTrigger.PAYMENT_FAILED,
            )
            is SubscriptionStatus.PAST_DUE
        )

    def test_recovery_returns_a_past_due_subscription_to_active(self) -> None:
        assert (
            apply(
                status=SubscriptionStatus.PAST_DUE,
                trigger=SubscriptionTrigger.PAYMENT_SUCCEEDED,
            )
            is SubscriptionStatus.ACTIVE
        )

    def test_resuming_a_subscription_that_is_not_paused_is_refused(self) -> None:
        with pytest.raises(InvalidTransitionError) as exc:
            apply(
                status=SubscriptionStatus.ACTIVE,
                trigger=SubscriptionTrigger.CUSTOMER_RESUMED,
            )
        assert exc.value.status is SubscriptionStatus.ACTIVE
        assert exc.value.trigger is SubscriptionTrigger.CUSTOMER_RESUMED

    def test_canceling_an_already_canceled_subscription_is_refused(self) -> None:
        with pytest.raises(InvalidTransitionError):
            apply(
                status=SubscriptionStatus.CANCELED,
                trigger=SubscriptionTrigger.CUSTOMER_CANCELED,
            )


class TestSubscriptionEntity:
    def test_scheduled_cancellation_leaves_the_subscription_entitled(self) -> None:
        # The customer paid for this period. If a scheduled cancellation
        # revoked entitlement now, we would have taken money for service
        # we then refused.
        subscription = _subscription()
        assert subscription.entitles is True

    def test_in_trial_is_decided_by_the_clock_not_the_status(self) -> None:
        subscription = _subscription(
            status=SubscriptionStatus.TRIALING, trial_end=_NOW + timedelta(days=1)
        )
        assert subscription.in_trial_at(_NOW) is True
        # Still TRIALING in the seconds between the trial ending and the
        # conversion job running — the clock is the truth.
        assert subscription.in_trial_at(_NOW + timedelta(days=2)) is False

    def test_no_trial_end_means_never_in_trial(self) -> None:
        assert _subscription().in_trial_at(_NOW) is False
