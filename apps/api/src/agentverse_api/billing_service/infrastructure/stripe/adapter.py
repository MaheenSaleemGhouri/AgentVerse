"""The Stripe adapter — the only module in this codebase that imports
the Stripe SDK.

Everything above it talks to `domain.payment_provider.PaymentProviderPort`
and its plain dataclasses. Adding a second provider, or replacing this
one, touches this directory and nothing else.

Three things this file is responsible for that are easy to get wrong:

**Not blocking the event loop.** The Stripe SDK's async surface is
uneven across resources, and a synchronous HTTP call inside `async def`
stalls every other request on the worker (Rule 12). Every call here goes
through `run_in_threadpool`, which is explicit, uniform, and does not
depend on which SDK methods happen to have async variants this release.

**Pinning the API version.** Passed on every call rather than inherited
from the account's dashboard default, so this service's behaviour is
decided by code under review rather than by a setting nobody in this
repo can see.

**Translating errors at the boundary.** A `stripe.StripeError` never
escapes this module. Callers get `ProviderError` with one bit that
actually changes their behaviour — whether retrying could help — because
a caller cannot do anything differently for `CardError` versus
`InvalidRequestError` except log a different word.

Price resolution deserves a note. Stripe needs a Price id, and this
system's source of truth for pricing is the `plans` table (ADR-0012).
Rather than keeping a second copy of the mapping in code, the adapter
looks up Stripe Prices by the metadata AgentVerse writes on them
(`agentverse_plan` / `agentverse_interval`) and caches the result for the
process's lifetime. A plan with no matching Price is a loud
configuration error, not a silent fallback to some other price.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, cast

import stripe
from starlette.concurrency import run_in_threadpool

from agentverse_api.billing_service.domain.payment_provider import (
    CheckoutSession,
    PortalSession,
    ProviderError,
    ProviderEvent,
    ProviderEventType,
    ProviderInvoice,
    ProviderPaymentMethod,
    ProviderSubscriptionState,
    WebhookVerificationError,
)
from agentverse_api.billing_service.domain.plan import BillingInterval, PlanTier

logger = logging.getLogger(__name__)

#: Stripe event types this system acts on, mapped into its own
#: vocabulary. Anything not listed is acknowledged and ignored — Stripe
#: sends dozens of types, and treating an unrecognized one as an error
#: would make every Stripe product launch an outage here.
_EVENT_TYPES: dict[str, ProviderEventType] = {
    "checkout.session.completed": ProviderEventType.CHECKOUT_COMPLETED,
    "customer.subscription.updated": ProviderEventType.SUBSCRIPTION_UPDATED,
    "customer.subscription.deleted": ProviderEventType.SUBSCRIPTION_DELETED,
    "invoice.paid": ProviderEventType.PAYMENT_SUCCEEDED,
    "invoice.payment_succeeded": ProviderEventType.PAYMENT_SUCCEEDED,
    "invoice.payment_failed": ProviderEventType.PAYMENT_FAILED,
}

#: Stripe error classes worth retrying. A rate limit or a transient API
#: error will likely succeed on a second attempt; a card decline or an
#: invalid request will not, and retrying it only wastes the customer's
#: time and ours.
_RETRYABLE = (stripe.RateLimitError, stripe.APIConnectionError)


def _instant(value: object) -> datetime | None:
    """Stripe sends Unix seconds. `None` and 0 both mean "not set"."""
    if not isinstance(value, int) or value == 0:
        return None
    return datetime.fromtimestamp(value, tz=UTC)


def _as_str(value: object) -> str | None:
    """Stripe expands some references into objects and leaves others as
    ids, depending on the request. Reading either shape without an
    `expand` round trip keeps a webhook handler from failing on a payload
    that is merely shaped differently than expected.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        nested = value.get("id")
        return nested if isinstance(nested, str) else None
    stripe_id = getattr(value, "id", None)
    return stripe_id if isinstance(stripe_id, str) else None


class StripePaymentProvider:
    """Implements `domain.payment_provider.PaymentProviderPort`."""

    def __init__(
        self,
        *,
        secret_key: str,
        webhook_secret: str,
        api_version: str,
        public_url: str,
    ) -> None:
        self._client = stripe.StripeClient(secret_key, stripe_version=api_version)
        self._webhook_secret = webhook_secret
        self._api_version = api_version
        self._public_url = public_url.rstrip("/")
        self._price_cache: dict[tuple[PlanTier, BillingInterval], str] = {}

    # ---- plumbing ----------------------------------------------------

    async def _call(self, fn: Any, /, *args: Any, **kwargs: Any) -> Any:
        """Every Stripe call goes through here: off the event loop, with
        errors translated at the boundary.
        """
        try:
            return await run_in_threadpool(lambda: fn(*args, **kwargs))
        except stripe.StripeError as exc:
            retryable = isinstance(exc, _RETRYABLE)
            # `user_message` is Stripe's customer-safe string; the raw
            # message can contain request details that do not belong in a
            # response body. Neither is logged with the payload.
            detail = exc.user_message or exc.__class__.__name__
            logger.warning(
                "stripe_call_failed",
                extra={"error_class": exc.__class__.__name__, "retryable": retryable},
            )
            raise ProviderError(detail, retryable=retryable) from exc

    async def _price_id(self, plan_slug: PlanTier, interval: BillingInterval) -> str:
        """Resolve a Stripe Price from the plan's own identity.

        Looked up by metadata rather than kept in a constant, so the
        `plans` table stays the single source of truth for what a tier is
        (Rule 3). Cached for the process lifetime: Prices are immutable
        in Stripe, so a cached id cannot go stale — changing a price
        means creating a new Price object, and the deploy that points at
        it restarts the process anyway.
        """
        key = (plan_slug, interval)
        cached = self._price_cache.get(key)
        if cached is not None:
            return cached
        result = await self._call(
            self._client.prices.search,
            params={
                "query": (
                    f"active:'true' AND metadata['agentverse_plan']:'{plan_slug.value}' "
                    f"AND metadata['agentverse_interval']:'{interval.value}'"
                ),
                "limit": 1,
            },
        )
        prices = list(result.data or [])
        if not prices:
            # Loud, not a fallback. Charging the wrong price is worse
            # than not charging at all, and a "nearest match" here would
            # do exactly that.
            raise ProviderError(
                f"No active Stripe Price is tagged for the {plan_slug.value} plan on the "
                f"{interval.value} interval. Run the price-sync step before enabling checkout."
            )
        price_id = str(prices[0].id)
        self._price_cache[key] = price_id
        return price_id

    # ---- customers ---------------------------------------------------

    async def ensure_customer(
        self, *, workspace_id: str, email: str | None, name: str | None
    ) -> str:
        # Searched by metadata rather than trusting a locally stored id
        # blindly: this is the call that repairs a workspace whose
        # customer row was lost, and it is idempotent by construction.
        found = await self._call(
            self._client.customers.search,
            params={"query": f"metadata['workspace_id']:'{workspace_id}'", "limit": 1},
        )
        existing = list(found.data or [])
        if existing:
            return str(existing[0].id)
        params: dict[str, Any] = {"metadata": {"workspace_id": workspace_id}}
        if email:
            params["email"] = email
        if name:
            params["name"] = name
        created = await self._call(self._client.customers.create, params=params)
        return str(created.id)

    # ---- checkout and portal -----------------------------------------

    async def create_checkout_session(
        self,
        *,
        workspace_id: str,
        provider_customer_id: str,
        plan_slug: PlanTier,
        interval: BillingInterval,
        success_url: str,
        cancel_url: str,
        trial_days: int | None,
        coupon_code: str | None,
    ) -> CheckoutSession:
        price_id = await self._price_id(plan_slug, interval)
        subscription_data: dict[str, Any] = {
            # Repeated on the subscription as well as the session: the
            # subscription outlives the session, and
            # `customer.subscription.*` events carry the subscription's
            # metadata, not the session's.
            "metadata": {
                "workspace_id": workspace_id,
                "plan": plan_slug.value,
                "interval": interval.value,
            }
        }
        if trial_days:
            subscription_data["trial_period_days"] = trial_days
        params: dict[str, Any] = {
            "mode": "subscription",
            "customer": provider_customer_id,
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            # Both, deliberately: `client_reference_id` is what shows in
            # the Stripe dashboard's session list during an incident,
            # metadata is what the webhook payload carries.
            "client_reference_id": workspace_id,
            "metadata": {
                "workspace_id": workspace_id,
                "plan": plan_slug.value,
                "interval": interval.value,
            },
            "subscription_data": subscription_data,
            # Lets the customer enter a code on Stripe's page rather than
            # this system validating one it does not own.
            "allow_promotion_codes": coupon_code is None,
            "automatic_tax": {"enabled": True},
            # Required for automatic tax on a subscription: Stripe needs
            # somewhere to derive jurisdiction from.
            "customer_update": {"address": "auto", "name": "auto"},
        }
        if coupon_code:
            params["discounts"] = [{"promotion_code": coupon_code}]
            # Stripe rejects `discounts` and `allow_promotion_codes`
            # together — an explicitly applied code wins.
            params.pop("allow_promotion_codes", None)
        session = await self._call(self._client.checkout.sessions.create, params=params)
        url = session.url
        if not url:
            raise ProviderError("Stripe returned a checkout session with no URL")
        return CheckoutSession(session_id=str(session.id), url=str(url))

    async def create_portal_session(
        self, *, provider_customer_id: str, return_url: str
    ) -> PortalSession:
        session = await self._call(
            self._client.billing_portal.sessions.create,
            params={"customer": provider_customer_id, "return_url": return_url},
        )
        return PortalSession(url=str(session.url))

    # ---- subscription mutations --------------------------------------

    async def cancel_subscription(
        self, *, provider_subscription_id: str, at_period_end: bool
    ) -> None:
        if at_period_end:
            await self._call(
                self._client.subscriptions.update,
                provider_subscription_id,
                params={"cancel_at_period_end": True},
            )
            return
        await self._call(self._client.subscriptions.cancel, provider_subscription_id)

    async def resume_subscription(self, *, provider_subscription_id: str) -> None:
        await self._call(
            self._client.subscriptions.update,
            provider_subscription_id,
            params={"cancel_at_period_end": False},
        )

    async def pause_subscription(self, *, provider_subscription_id: str) -> None:
        # `void` rather than `keep_as_draft`: invoices generated while
        # paused should not exist at all, not sit as drafts that someone
        # could later finalize and charge for service never rendered.
        await self._call(
            self._client.subscriptions.update,
            provider_subscription_id,
            params={"pause_collection": {"behavior": "void"}},
        )

    async def unpause_subscription(self, *, provider_subscription_id: str) -> None:
        await self._call(
            self._client.subscriptions.update,
            provider_subscription_id,
            params={"pause_collection": ""},
        )

    async def change_subscription_plan(
        self,
        *,
        provider_subscription_id: str,
        plan_slug: PlanTier,
        interval: BillingInterval,
    ) -> None:
        price_id = await self._price_id(plan_slug, interval)
        current = await self._call(self._client.subscriptions.retrieve, provider_subscription_id)
        items = list(current["items"].data or []) if current.get("items") else []
        if not items:
            raise ProviderError(
                f"Stripe subscription {provider_subscription_id} has no line items to change"
            )
        await self._call(
            self._client.subscriptions.update,
            provider_subscription_id,
            params={
                "items": [{"id": str(items[0].id), "price": price_id}],
                # `create_prorations`, not `none`: the customer is
                # switching mid-cycle and both sides must agree on what
                # that is worth. This system computes the same figure
                # independently for its own invoice line.
                "proration_behavior": "create_prorations",
            },
        )

    async def refund_payment(
        self, *, provider_invoice_id: str, amount_cents: int | None, reason: str | None
    ) -> str:
        invoice = await self._call(self._client.invoices.retrieve, provider_invoice_id)
        payment_intent = _as_str(invoice.get("payment_intent"))
        if payment_intent is None:
            raise ProviderError(
                f"Invoice {provider_invoice_id} has no payment to refund "
                "(it may be unpaid, voided, or settled outside Stripe)"
            )
        params: dict[str, Any] = {"payment_intent": payment_intent}
        if amount_cents is not None:
            params["amount"] = amount_cents
        if reason:
            # Free text goes to metadata; Stripe's own `reason` accepts
            # only a fixed vocabulary, and forcing an operator's note
            # into it would either fail or lose the note.
            params["metadata"] = {"agentverse_reason": reason}
        refund = await self._call(self._client.refunds.create, params=params)
        return str(refund.id)

    # ---- reads -------------------------------------------------------

    async def list_invoices(
        self, *, provider_customer_id: str, limit: int
    ) -> list[ProviderInvoice]:
        result = await self._call(
            self._client.invoices.list,
            params={"customer": provider_customer_id, "limit": limit},
        )
        return [self._to_invoice(row) for row in (result.data or [])]

    @staticmethod
    def _to_invoice(row: Any) -> ProviderInvoice:
        created = _instant(row.get("created")) or datetime.now(UTC)
        return ProviderInvoice(
            id=str(row.id),
            number=cast(str | None, row.get("number")),
            status=str(row.get("status") or "unknown"),
            amount_due_cents=int(row.get("amount_due") or 0),
            amount_paid_cents=int(row.get("amount_paid") or 0),
            currency=str(row.get("currency") or "usd"),
            created_at=created,
            period_start=_instant(row.get("period_start")),
            period_end=_instant(row.get("period_end")),
            hosted_invoice_url=cast(str | None, row.get("hosted_invoice_url")),
            invoice_pdf_url=cast(str | None, row.get("invoice_pdf")),
        )

    async def list_payment_methods(
        self, *, provider_customer_id: str
    ) -> list[ProviderPaymentMethod]:
        customer = await self._call(self._client.customers.retrieve, provider_customer_id)
        settings = customer.get("invoice_settings") or {}
        default_id = _as_str(settings.get("default_payment_method"))
        result = await self._call(
            self._client.payment_methods.list,
            params={"customer": provider_customer_id, "type": "card"},
        )
        methods: list[ProviderPaymentMethod] = []
        for row in result.data or []:
            card = row.get("card") or {}
            methods.append(
                ProviderPaymentMethod(
                    id=str(row.id),
                    # Brand, last four and expiry only. There is nowhere
                    # in this codebase for a PAN or CVC to be stored, and
                    # that is the PCI posture — a property of the schema,
                    # not of a policy.
                    brand=cast(str | None, card.get("brand")),
                    last4=cast(str | None, card.get("last4")),
                    exp_month=cast(int | None, card.get("exp_month")),
                    exp_year=cast(int | None, card.get("exp_year")),
                    is_default=str(row.id) == default_id,
                )
            )
        return methods

    async def get_subscription_state(
        self, *, provider_subscription_id: str
    ) -> ProviderSubscriptionState | None:
        try:
            row = await self._call(self._client.subscriptions.retrieve, provider_subscription_id)
        except ProviderError:
            # A subscription Stripe has never heard of is a real
            # reconciliation finding — "our row points at nothing" — not
            # a failure of the reconciliation run.
            return None
        return ProviderSubscriptionState(
            id=str(row.id),
            status=str(row.get("status") or "unknown"),
            current_period_start=_instant(row.get("current_period_start")),
            current_period_end=_instant(row.get("current_period_end")),
            cancel_at_period_end=bool(row.get("cancel_at_period_end")),
            canceled_at=_instant(row.get("canceled_at")),
        )

    # ---- webhooks ----------------------------------------------------

    def verify_webhook(self, *, payload: bytes, signature: str) -> ProviderEvent | None:
        """Verify against the raw bytes, then translate.

        `stripe.Webhook.construct_event` checks the HMAC *and* the
        timestamp tolerance, so a captured payload cannot be replayed
        indefinitely. The payload is not parsed before this succeeds.
        """
        try:
            # `construct_event` is unannotated in stripe 12.x, so mypy
            # cannot see through it. Suppressed here rather than made
            # `Any` at a wider scope: this is the only call site, and the
            # return value is immediately narrowed by `_translate`.
            event = stripe.Webhook.construct_event(  # type: ignore[no-untyped-call]
                payload, signature, self._webhook_secret
            )
        except (ValueError, stripe.SignatureVerificationError) as exc:
            # No detail in the message and none in the log: telling a
            # forger whether the timestamp or the digest was wrong helps
            # them iterate.
            logger.warning("stripe_webhook_signature_rejected")
            raise WebhookVerificationError from exc
        return self._translate(event)

    @staticmethod
    def _translate(event: Any) -> ProviderEvent | None:
        mapped = _EVENT_TYPES.get(str(event["type"]))
        if mapped is None:
            return None
        obj = event["data"]["object"]
        metadata = obj.get("metadata") or {}
        workspace_id = metadata.get("workspace_id") or obj.get("client_reference_id")

        if mapped is ProviderEventType.CHECKOUT_COMPLETED:
            subscription_id = _as_str(obj.get("subscription"))
        elif mapped in (
            ProviderEventType.SUBSCRIPTION_UPDATED,
            ProviderEventType.SUBSCRIPTION_DELETED,
        ):
            # On a subscription event the object *is* the subscription.
            subscription_id = str(obj.get("id")) if obj.get("id") else None
        else:
            subscription_id = _as_str(obj.get("subscription"))

        return ProviderEvent(
            event_id=str(event["id"]),
            type=mapped,
            occurred_at=_instant(event.get("created")) or datetime.now(UTC),
            workspace_id=workspace_id if isinstance(workspace_id, str) else None,
            provider_customer_id=_as_str(obj.get("customer")),
            provider_subscription_id=subscription_id,
            data={
                "status": obj.get("status"),
                "cancel_at_period_end": obj.get("cancel_at_period_end"),
                "amount_paid_cents": obj.get("amount_paid"),
                "invoice_id": obj.get("id") if mapped.name.startswith("PAYMENT") else None,
                # Written by `create_checkout_session` onto both the
                # session and the subscription, so a checkout event can
                # be resolved to a plan without a second API call.
                "plan": metadata.get("plan"),
                "interval": metadata.get("interval"),
            },
        )
