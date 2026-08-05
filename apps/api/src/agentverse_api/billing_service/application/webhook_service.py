"""Turning verified provider events into subscription state changes.

The shape is fixed and deliberate: **claim → dispatch → resolve**, all in
one transaction.

*Claim* inserts the delivery row and loses to a concurrent duplicate at
the unique index. A claim that fails means another delivery of the same
event owns it, and this one returns without doing anything — the correct
answer, not an error.

*Dispatch* translates the event into a call on `SubscriptionService`.
This module contains no state-machine logic of its own: every transition
goes through the same functions the rest of the system uses. Two copies
of "what does a failed payment mean" is exactly the divergence that makes
billing bugs unfindable, and it is the mistake `stripe-integration-expert`
names first.

*Resolve* marks the row processed. Because it shares the transaction
with the state change, a crash rolls both back together — so a row left
at `received` is a genuine signal that something was received and lost,
which the reconciliation sweep looks for.

**Out-of-order delivery is assumed, not hoped against.** Providers do not
guarantee that events arrive in the order they were generated. Handlers
here either move to a state that is idempotent under repetition, or check
the current state before acting, rather than blindly overwriting with a
possibly-stale payload.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.application.subscription_service import (
    SubscriptionService,
)
from agentverse_api.billing_service.domain.customer import PaymentProvider
from agentverse_api.billing_service.domain.exceptions import SubscriptionNotFoundError
from agentverse_api.billing_service.domain.payment_provider import (
    ProviderEvent,
    ProviderEventType,
)
from agentverse_api.billing_service.domain.plan import BillingInterval, PlanTier
from agentverse_api.billing_service.domain.ports import WebhookEventRepository
from agentverse_api.billing_service.domain.subscription import (
    InvalidTransitionError,
    SubscriptionStatus,
)

logger = logging.getLogger(__name__)

#: Actor recorded on transitions the provider caused. Distinguishable
#: from `system:billing` (a scheduled job) and from a user id, so the
#: event log answers "who did this" for every row.
PROVIDER_ACTOR = "provider:stripe"


class WebhookOutcome(StrEnum):
    """What happened, for the delivery log and for the response body.

    `DUPLICATE` and `IGNORED` are both successes: the first means the
    provider retried, the second means it sent something this system does
    not act on. Neither should read as a failure in a dashboard, which is
    why they are distinct values rather than both folded into "ok".
    """

    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    IGNORED = "ignored"
    FAILED = "failed"


@dataclass(slots=True)
class WebhookService:
    events: WebhookEventRepository
    subscriptions: SubscriptionService
    catalog: PlanCatalogService
    provider_name: str = PaymentProvider.STRIPE.value

    async def handle(self, event: ProviderEvent) -> WebhookOutcome:
        """Process one verified event, exactly once."""
        claimed = await self.events.claim(
            provider=self.provider_name,
            provider_event_id=event.event_id,
            event_type=event.type.value,
            workspace_id=event.workspace_id,
        )
        if not claimed:
            logger.info(
                "billing_webhook_duplicate",
                extra={"provider_event_id": event.event_id, "event_type": event.type.value},
            )
            return WebhookOutcome.DUPLICATE

        try:
            handled = await self._dispatch(event)
        except Exception as exc:
            # Recorded, not swallowed. The route re-raises so the caller
            # sees a 5xx and the provider retries — but the row now says
            # this event was seen and why it failed, which is the only
            # trail a billing dispute has to follow.
            await self.events.resolve(
                provider=self.provider_name,
                provider_event_id=event.event_id,
                status=WebhookOutcome.FAILED.value,
                error=f"{type(exc).__name__}: {exc}",
            )
            logger.exception(
                "billing_webhook_failed",
                extra={"provider_event_id": event.event_id, "event_type": event.type.value},
            )
            raise

        outcome = WebhookOutcome.PROCESSED if handled else WebhookOutcome.IGNORED
        await self.events.resolve(
            provider=self.provider_name,
            provider_event_id=event.event_id,
            status=outcome.value,
            error=None,
        )
        return outcome

    async def _dispatch(self, event: ProviderEvent) -> bool:
        """Route to the per-event handler. `False` means "verified, but
        nothing here acts on it" — not a failure.
        """
        if event.workspace_id is None:
            # Unattributable. Recorded by the claim above so it is
            # visible, but there is no workspace whose state could
            # change. Silently dropping it would hide a real
            # misconfiguration (a customer created outside the product).
            logger.warning(
                "billing_webhook_unattributed",
                extra={"provider_event_id": event.event_id, "event_type": event.type.value},
            )
            return False

        match event.type:
            case ProviderEventType.CHECKOUT_COMPLETED:
                return await self._on_checkout_completed(event)
            case ProviderEventType.PAYMENT_SUCCEEDED:
                return await self._on_payment_succeeded(event)
            case ProviderEventType.PAYMENT_FAILED:
                return await self._on_payment_failed(event)
            case ProviderEventType.SUBSCRIPTION_UPDATED:
                return await self._on_subscription_updated(event)
            case ProviderEventType.SUBSCRIPTION_DELETED:
                return await self._on_subscription_deleted(event)

    async def _on_checkout_completed(self, event: ProviderEvent) -> bool:
        """A customer finished paying. Open the subscription if this is
        their first, or do nothing if a race already opened it.

        The customer link is written first and unconditionally: it is how
        every later portal session, invoice list and refund finds this
        workspace's account, and it must survive even if the subscription
        half fails.
        """
        assert event.workspace_id is not None  # noqa: S101 - checked in _dispatch
        if event.provider_customer_id:
            await self.subscriptions.link_customer(
                workspace_id=event.workspace_id,
                provider=PaymentProvider.STRIPE,
                provider_customer_id=event.provider_customer_id,
            )
        existing = await self.subscriptions.current(event.workspace_id)
        if existing is not None:
            # Already open — a duplicate checkout, or an out-of-order
            # delivery arriving after a subscription event. Opening a
            # second one would bill the workspace twice.
            return False
        plan_slug = self._plan_from(event)
        if plan_slug is None:
            logger.warning(
                "billing_webhook_checkout_without_plan",
                extra={"provider_event_id": event.event_id},
            )
            return False
        plan = await self.catalog.get_plan(plan_slug)
        await self.subscriptions.start(
            workspace_id=event.workspace_id,
            plan_slug=plan_slug,
            interval=self._interval_from(event),
            actor=PROVIDER_ACTOR,
            # The provider's event id, so a redelivery that somehow got
            # past the claim still cannot open a second subscription.
            idempotency_key=f"{self.provider_name}:{event.event_id}",
            # Checkout already collected payment details; whether a trial
            # applies was decided when the session was created, and the
            # provider is the authority on what it actually granted.
            with_trial=bool(plan.trial_days) and event.data.get("status") == "trialing",
            provider_subscription_id=event.provider_subscription_id,
        )
        return True

    async def _on_payment_succeeded(self, event: ProviderEvent) -> bool:
        assert event.workspace_id is not None  # noqa: S101 - checked in _dispatch
        try:
            await self.subscriptions.payment_succeeded(
                workspace_id=event.workspace_id,
                idempotency_key=f"{self.provider_name}:{event.event_id}",
                actor=PROVIDER_ACTOR,
                reason="invoice paid",
            )
        except SubscriptionNotFoundError:
            # A payment for a workspace with no live subscription. Real
            # when an invoice settles after cancellation. Nothing to
            # transition, and inventing a subscription from a payment
            # event would resurrect a customer who left.
            return False
        except InvalidTransitionError:
            # Out-of-order: e.g. a paused subscription that cannot accept
            # a payment trigger. Refusing beats forcing the state
            # machine, which is what it exists to prevent.
            logger.warning(
                "billing_webhook_out_of_order",
                extra={"provider_event_id": event.event_id, "event_type": event.type.value},
            )
            return False
        return True

    async def _on_payment_failed(self, event: ProviderEvent) -> bool:
        assert event.workspace_id is not None  # noqa: S101 - checked in _dispatch
        try:
            await self.subscriptions.payment_failed(
                workspace_id=event.workspace_id,
                idempotency_key=f"{self.provider_name}:{event.event_id}",
                actor=PROVIDER_ACTOR,
                reason="invoice payment failed",
            )
        except (SubscriptionNotFoundError, InvalidTransitionError):
            return False
        return True

    async def _on_subscription_updated(self, event: ProviderEvent) -> bool:
        """Mirror a provider-side change made outside this product.

        The Billing Portal lets a customer cancel or change plan without
        ever touching an AgentVerse endpoint, so this handler is the only
        way that reaches this database. It syncs the one field the portal
        can change that is not already covered by a payment event —
        whether a cancellation is scheduled — and leaves status
        transitions to the payment and deletion events, which carry
        unambiguous meaning.
        """
        assert event.workspace_id is not None  # noqa: S101 - checked in _dispatch
        subscription = await self.subscriptions.current(event.workspace_id)
        if subscription is None:
            return False
        scheduled = bool(event.data.get("cancel_at_period_end"))
        if scheduled == subscription.cancel_at_period_end:
            return False
        if scheduled:
            await self.subscriptions.cancel(
                workspace_id=event.workspace_id,
                actor=PROVIDER_ACTOR,
                idempotency_key=f"{self.provider_name}:{event.event_id}",
                at_period_end=True,
            )
        else:
            await self.subscriptions.resume_scheduled_cancellation(workspace_id=event.workspace_id)
        return True

    async def _on_subscription_deleted(self, event: ProviderEvent) -> bool:
        assert event.workspace_id is not None  # noqa: S101 - checked in _dispatch
        subscription = await self.subscriptions.current(event.workspace_id)
        if subscription is None or subscription.status is SubscriptionStatus.CANCELED:
            return False
        await self.subscriptions.cancel(
            workspace_id=event.workspace_id,
            actor=PROVIDER_ACTOR,
            idempotency_key=f"{self.provider_name}:{event.event_id}",
            at_period_end=False,
            reason="subscription ended at the payment provider",
        )
        return True

    @staticmethod
    def _plan_from(event: ProviderEvent) -> PlanTier | None:
        raw = event.data.get("plan")
        if not isinstance(raw, str):
            return None
        try:
            return PlanTier(raw)
        except ValueError:
            return None

    @staticmethod
    def _interval_from(event: ProviderEvent) -> BillingInterval:
        raw = event.data.get("interval")
        if isinstance(raw, str):
            try:
                return BillingInterval(raw)
            except ValueError:
                pass
        return BillingInterval.MONTHLY
