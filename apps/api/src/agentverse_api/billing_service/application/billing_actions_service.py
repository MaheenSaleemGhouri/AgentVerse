"""The actions that move money, or that need the payment provider to
answer.

Everything here follows one rule: **the provider acts first, and this
database follows via the webhook.** A cancel endpoint that flipped the
local status and then called the provider would leave a customer marked
canceled here and still charged there if the second call failed. So these
methods call the provider and let the resulting event carry the state
change — with two deliberate exceptions, marked at their call sites,
where the local change is the *only* durable record of an intent the
provider does not model.

Reads (invoices, payment methods) go straight to the provider rather than
to a local mirror. Invoice PDFs and card details are the provider's to
hold, and a cached copy here would be one more thing that can be stale
and one more place a card's last four digits lives.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.application.subscription_service import SubscriptionService
from agentverse_api.billing_service.domain.customer import PaymentProvider
from agentverse_api.billing_service.domain.exceptions import (
    PlanNotPurchasableError,
    SubscriptionAlreadyExistsError,
    SubscriptionNotFoundError,
)
from agentverse_api.billing_service.domain.payment_provider import (
    CheckoutSession,
    PaymentProviderPort,
    PortalSession,
    ProviderError,
    ProviderInvoice,
    ProviderPaymentMethod,
)
from agentverse_api.billing_service.domain.plan import (
    BillingInterval,
    PlanTier,
    is_upgrade,
    price_cents,
)
from agentverse_api.billing_service.domain.ports import CustomerRepository
from agentverse_api.billing_service.domain.proration import Proration, prorate
from agentverse_api.billing_service.domain.subscription import Subscription


@dataclass(frozen=True, slots=True)
class PlanChangeQuote:
    """What a plan change will cost, before it is made.

    Computed by this system rather than read back from the provider: a
    number this codebase cannot recompute from stored timestamps is a
    number nobody can defend in a dispute. The provider computes its own
    proration for the actual charge, using the same exact-time math
    against the same period boundaries, so the two agree.
    """

    from_plan: PlanTier
    to_plan: PlanTier
    interval: BillingInterval
    proration: Proration
    is_upgrade: bool


@dataclass(slots=True)
class BillingActionsService:
    provider: PaymentProviderPort
    subscriptions: SubscriptionService
    customers: CustomerRepository
    catalog: PlanCatalogService

    # ---- entry points ------------------------------------------------

    async def start_checkout(
        self,
        *,
        workspace_id: str,
        plan_slug: PlanTier,
        interval: BillingInterval,
        success_url: str,
        cancel_url: str,
        billing_email: str | None,
        workspace_name: str | None,
        coupon_code: str | None = None,
    ) -> CheckoutSession:
        """Hand the browser a provider-hosted page to pay on.

        No subscription row is created here. It is created when the
        provider confirms payment, via `checkout.session.completed` —
        creating it optimistically would leave a phantom subscription for
        every customer who opened checkout and closed the tab.
        """
        if await self.subscriptions.current(workspace_id) is not None:
            raise SubscriptionAlreadyExistsError(workspace_id)
        plan = await self.catalog.get_plan(plan_slug)
        if plan.is_custom_priced:
            raise PlanNotPurchasableError(
                plan_slug.value, "custom-priced tiers are quoted by sales, not self-served"
            )
        customer_id = await self._ensure_customer(
            workspace_id=workspace_id, email=billing_email, name=workspace_name
        )
        return await self.provider.create_checkout_session(
            workspace_id=workspace_id,
            provider_customer_id=customer_id,
            plan_slug=plan_slug,
            interval=interval,
            success_url=success_url,
            cancel_url=cancel_url,
            trial_days=plan.trial_days or None,
            coupon_code=coupon_code,
        )

    async def open_portal(self, *, workspace_id: str, return_url: str) -> PortalSession:
        """The provider's own management surface: payment methods, plan
        changes, cancellation, invoice history.

        Preferred over building each of those here — it is where the card
        form lives, and every screen this product does not build to
        collect card data is PCI scope this product does not carry.
        """
        customer = await self.customers.get_for_workspace(workspace_id)
        if customer is None:
            raise SubscriptionNotFoundError(workspace_id)
        return await self.provider.create_portal_session(
            provider_customer_id=customer.provider_customer_id, return_url=return_url
        )

    # ---- subscription mutations --------------------------------------

    async def cancel(
        self, *, workspace_id: str, actor: str, at_period_end: bool, reason: str | None = None
    ) -> Subscription:
        """Cancel at the provider, then record the intent locally.

        The provider call goes first: if it fails, nothing local has
        changed and the customer is still correctly subscribed. The local
        write that follows is one of the two deliberate exceptions to
        "let the webhook do it" — `cancel_at_period_end` is an intent the
        customer expects to see reflected immediately, and the provider's
        `customer.subscription.updated` event confirming it may be
        seconds behind.
        """
        subscription = await self.subscriptions.require_current(workspace_id)
        if subscription.provider_subscription_id:
            await self.provider.cancel_subscription(
                provider_subscription_id=subscription.provider_subscription_id,
                at_period_end=at_period_end,
            )
        return await self.subscriptions.cancel(
            workspace_id=workspace_id,
            actor=actor,
            idempotency_key=f"cancel:{subscription.id}:{at_period_end}",
            at_period_end=at_period_end,
            reason=reason,
        )

    async def resume(self, *, workspace_id: str) -> Subscription:
        """Undo a scheduled cancellation. The second deliberate local
        write, for the same reason as `cancel`.
        """
        subscription = await self.subscriptions.require_current(workspace_id)
        if subscription.provider_subscription_id:
            await self.provider.resume_subscription(
                provider_subscription_id=subscription.provider_subscription_id
            )
        return await self.subscriptions.resume_scheduled_cancellation(workspace_id=workspace_id)

    async def pause(self, *, workspace_id: str, actor: str) -> Subscription:
        subscription = await self.subscriptions.require_current(workspace_id)
        if subscription.provider_subscription_id:
            await self.provider.pause_subscription(
                provider_subscription_id=subscription.provider_subscription_id
            )
        return await self.subscriptions.pause(
            workspace_id=workspace_id,
            actor=actor,
            idempotency_key=f"pause:{subscription.id}:{subscription.updated_at.isoformat()}",
        )

    async def unpause(self, *, workspace_id: str, actor: str) -> Subscription:
        subscription = await self.subscriptions.require_current(workspace_id)
        if subscription.provider_subscription_id:
            await self.provider.unpause_subscription(
                provider_subscription_id=subscription.provider_subscription_id
            )
        return await self.subscriptions.resume(
            workspace_id=workspace_id,
            actor=actor,
            idempotency_key=f"unpause:{subscription.id}:{subscription.updated_at.isoformat()}",
        )

    async def quote_plan_change(
        self, *, workspace_id: str, target_slug: PlanTier, interval: BillingInterval
    ) -> PlanChangeQuote:
        """What this change costs, without making it.

        Shown before the confirm button. `saas-strategist`'s standard is
        that proration appears as a clear line item *before or on* the
        invoice — a customer should never first learn the number from
        their statement.
        """
        subscription = await self.subscriptions.require_current(workspace_id)
        current_plan = await self.catalog.get_plan(subscription.plan_slug)
        target_plan = await self.catalog.get_plan(target_slug)
        if target_plan.is_custom_priced:
            raise PlanNotPurchasableError(
                target_slug.value, "custom-priced tiers are quoted by sales, not self-served"
            )
        quote = prorate(
            old_price_cents=price_cents(current_plan, subscription.interval) or 0,
            new_price_cents=price_cents(target_plan, interval) or 0,
            period_start=subscription.current_period_start,
            period_end=subscription.current_period_end,
            change_at=self.subscriptions.now(),
        )
        return PlanChangeQuote(
            from_plan=subscription.plan_slug,
            to_plan=target_slug,
            interval=interval,
            proration=quote,
            is_upgrade=is_upgrade(current=subscription.plan_slug, target=target_slug),
        )

    async def change_plan(
        self,
        *,
        workspace_id: str,
        target_slug: PlanTier,
        interval: BillingInterval,
        actor: str,
        idempotency_key: str,
    ) -> tuple[Subscription, Proration]:
        """Move the provider first, then this system's own record.

        Ordering matters and is not symmetric: if the provider call
        succeeds and the local one fails, the next
        `customer.subscription.updated` event and the reconciliation
        sweep both repair it. If the local one succeeded first and the
        provider call failed, this system would be serving and invoicing
        a plan the customer is not being charged for, with nothing to
        detect it.
        """
        subscription = await self.subscriptions.require_current(workspace_id)
        if subscription.provider_subscription_id:
            await self.provider.change_subscription_plan(
                provider_subscription_id=subscription.provider_subscription_id,
                plan_slug=target_slug,
                interval=interval,
            )
        return await self.subscriptions.change_plan(
            workspace_id=workspace_id,
            target_slug=target_slug,
            interval=interval,
            actor=actor,
            idempotency_key=idempotency_key,
        )

    # ---- reads straight from the provider ----------------------------

    async def list_invoices(self, *, workspace_id: str, limit: int = 24) -> list[ProviderInvoice]:
        """Empty list, not an error, for a workspace that never paid —
        the invoice table should render its empty state.
        """
        customer = await self.customers.get_for_workspace(workspace_id)
        if customer is None:
            return []
        return await self.provider.list_invoices(
            provider_customer_id=customer.provider_customer_id, limit=limit
        )

    async def list_payment_methods(self, *, workspace_id: str) -> list[ProviderPaymentMethod]:
        customer = await self.customers.get_for_workspace(workspace_id)
        if customer is None:
            return []
        return await self.provider.list_payment_methods(
            provider_customer_id=customer.provider_customer_id
        )

    async def refund(
        self,
        *,
        workspace_id: str,
        invoice_id: str,
        amount_cents: int | None,
        reason: str | None,
    ) -> str:
        """Refund an invoice. Never automatic.

        A downgrade produces a credit against the next invoice; money
        actually leaving the company is a separate, deliberately
        authorized action. The invoice is checked to belong to this
        workspace's customer first — without that, an invoice id from
        another tenant would refund their charge (Rule 11).
        """
        customer = await self.customers.get_for_workspace(workspace_id)
        if customer is None:
            raise SubscriptionNotFoundError(workspace_id)
        invoices = await self.provider.list_invoices(
            provider_customer_id=customer.provider_customer_id, limit=100
        )
        if not any(invoice.id == invoice_id for invoice in invoices):
            # Not 403: confirming the invoice exists but belongs to
            # someone else leaks its existence across tenants.
            raise ProviderError(f"No invoice {invoice_id!r} for this workspace")
        return await self.provider.refund_payment(
            provider_invoice_id=invoice_id, amount_cents=amount_cents, reason=reason
        )

    # ---- helpers -----------------------------------------------------

    async def _ensure_customer(
        self, *, workspace_id: str, email: str | None, name: str | None
    ) -> str:
        existing = await self.customers.get_for_workspace(workspace_id)
        if existing is not None:
            return existing.provider_customer_id
        provider_customer_id = await self.provider.ensure_customer(
            workspace_id=workspace_id, email=email, name=name
        )
        linked = await self.customers.upsert(
            workspace_id=workspace_id,
            provider=PaymentProvider.STRIPE,
            provider_customer_id=provider_customer_id,
            billing_email=email,
        )
        return linked.provider_customer_id
