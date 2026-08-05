"""The payment-provider port.

Nothing above `infrastructure/stripe/` imports the Stripe SDK, mentions a
Stripe object shape, or knows a `cus_`/`sub_`/`in_` prefix exists. The
application layer talks to this Protocol and to the plain dataclasses
below; the adapter translates. That is the same provider-abstraction rule
CLAUDE.md Rule 16 sets for LLM providers, applied here for the same
reason — a vendor SDK reaching into use-case code makes the vendor
unswappable and the use case untestable.

**Why these types are not just Stripe's, renamed.** Each one carries
only what AgentVerse actually decides with. A Stripe `Invoice` has
around sixty fields; this system reads seven of them, and a
`ProviderInvoice` that mirrored all sixty would quietly become a place
for Stripe-specific reasoning to accumulate outside the adapter.

**Money stays integer cents** (Rule 15). Stripe also uses minor units,
so there is no conversion — but the types say so explicitly rather than
relying on that continuing to be true.

**Verification is part of the port, not a detail of it.**
`verify_webhook` takes the raw request body, because signature
verification over a re-serialized payload verifies nothing: JSON
round-tripping can reorder keys and renormalize numbers, and the
signature was computed over the original bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from agentverse_api.billing_service.domain.plan import BillingInterval, PlanTier


class ProviderError(Exception):
    """The provider rejected a call or was unreachable. Maps to HTTP 502.

    Deliberately one exception rather than a taxonomy mirroring Stripe's
    error classes: the caller's options are the same for all of them
    (surface a retryable failure), and a taxonomy would be Stripe's
    vocabulary leaking through the port it exists to hide. `retryable`
    carries the one distinction that changes behaviour.
    """

    def __init__(self, detail: str, *, retryable: bool = False) -> None:
        self.detail = detail
        self.retryable = retryable
        super().__init__(detail)


class ProviderNotConfiguredError(Exception):
    """No payment provider credentials in this environment. Maps to 503.

    A first-class state, not an error condition: local development, CI,
    and preview environments legitimately run without Stripe keys. The
    routes that need a provider answer 503 with a clear message rather
    than 500-ing on a `None`, which is the same shape the OAuth catalog
    already uses for a provider AgentVerse has not registered an app
    with.
    """

    def __init__(self) -> None:
        super().__init__(
            "No payment provider is configured in this environment; "
            "billing actions that move money are unavailable."
        )


class ProviderEventType(StrEnum):
    """The provider events this system acts on, in its own vocabulary.

    A closed set on purpose. An event absent from here is acknowledged
    and ignored rather than dispatched — Stripe sends dozens of event
    types, and silently doing nothing with an unrecognized one is
    correct, while failing on it would make every new Stripe event type
    an outage.
    """

    CHECKOUT_COMPLETED = "checkout_completed"
    SUBSCRIPTION_UPDATED = "subscription_updated"
    SUBSCRIPTION_DELETED = "subscription_deleted"
    PAYMENT_SUCCEEDED = "payment_succeeded"
    PAYMENT_FAILED = "payment_failed"


@dataclass(frozen=True, slots=True)
class ProviderEvent:
    """A verified provider event, translated.

    `event_id` is the provider's own identifier and the idempotency key:
    the provider guarantees at-least-once delivery, so the same
    `event_id` will arrive more than once and must produce the same end
    state.

    `occurred_at` exists because delivery order is not generation order.
    A handler that assumes otherwise can apply a stale update over a
    fresher one.
    """

    event_id: str
    type: ProviderEventType
    occurred_at: datetime
    workspace_id: str | None
    provider_customer_id: str | None
    provider_subscription_id: str | None
    #: Only the fields a handler reads, already extracted by the adapter.
    data: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CheckoutSession:
    """Where to send the browser to pay.

    The URL is all this system needs. Card details are collected on the
    provider's hosted page and never reach AgentVerse's servers, logs, or
    database — which is what keeps this platform in the smallest PCI
    scope, and is a property of *not* having a card field anywhere in
    this codebase rather than of a policy document.
    """

    session_id: str
    url: str


@dataclass(frozen=True, slots=True)
class PortalSession:
    """Where to send the browser to manage an existing subscription."""

    url: str


@dataclass(frozen=True, slots=True)
class ProviderInvoice:
    id: str
    number: str | None
    status: str
    #: Integer minor units (cents), matching Rule 15 and the provider's
    #: own representation.
    amount_due_cents: int
    amount_paid_cents: int
    currency: str
    created_at: datetime
    period_start: datetime | None
    period_end: datetime | None
    #: Provider-hosted links. Never proxied through this service: they
    #: are short-lived, signed, and re-serving them would put invoice
    #: PDFs through infrastructure that has no reason to hold them.
    hosted_invoice_url: str | None
    invoice_pdf_url: str | None


@dataclass(frozen=True, slots=True)
class ProviderPaymentMethod:
    """The non-sensitive remainder of a card.

    Brand, last four, and expiry are the only card-derived values this
    system ever holds, and it holds them transiently — read from the
    provider per request, never stored. A PAN, CVC, or full expiry-plus-
    number combination has no field to live in here, which is the point.
    """

    id: str
    brand: str | None
    last4: str | None
    exp_month: int | None
    exp_year: int | None
    is_default: bool


@dataclass(frozen=True, slots=True)
class ProviderSubscriptionState:
    """What the provider believes about a subscription.

    Used only by reconciliation. The provider is the source of truth for
    payment facts; this system's `billing_subscriptions` is a projection
    of that truth, and this type is how the two are compared.
    """

    id: str
    status: str
    current_period_start: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    canceled_at: datetime | None


class PaymentProviderPort(Protocol):
    """Everything AgentVerse asks a payment provider to do.

    Every method is async: each is a network call, and a synchronous one
    inside `async def` would block the event loop (Rule 12).
    """

    async def ensure_customer(
        self, *, workspace_id: str, email: str | None, name: str | None
    ) -> str:
        """The provider's customer id for this workspace, creating it if
        needed. `workspace_id` is written into the provider's metadata so
        the mapping is queryable from the provider's own dashboard during
        an incident, not only from this database.
        """
        ...

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
    ) -> CheckoutSession: ...

    async def create_portal_session(
        self, *, provider_customer_id: str, return_url: str
    ) -> PortalSession: ...

    async def cancel_subscription(
        self, *, provider_subscription_id: str, at_period_end: bool
    ) -> None: ...

    async def resume_subscription(self, *, provider_subscription_id: str) -> None:
        """Undo a scheduled cancellation while the period is still open."""
        ...

    async def pause_subscription(self, *, provider_subscription_id: str) -> None: ...

    async def unpause_subscription(self, *, provider_subscription_id: str) -> None: ...

    async def change_subscription_plan(
        self,
        *,
        provider_subscription_id: str,
        plan_slug: PlanTier,
        interval: BillingInterval,
    ) -> None:
        """Move the provider-side subscription to another price.

        Proration is computed by this system (`domain/proration.py`) for
        display and for its own invoice lines; the provider computes its
        own for the actual charge. Both use exact-time math against the
        same period boundaries, so they agree — but this system never
        asks the provider what the proration *is*, because a number it
        cannot recompute is a number it cannot defend in a dispute.
        """
        ...

    async def list_invoices(
        self, *, provider_customer_id: str, limit: int
    ) -> list[ProviderInvoice]: ...

    async def list_payment_methods(
        self, *, provider_customer_id: str
    ) -> list[ProviderPaymentMethod]: ...

    async def refund_payment(
        self, *, provider_invoice_id: str, amount_cents: int | None, reason: str | None
    ) -> str:
        """Refund an invoice's charge, fully or partially. Returns the
        provider's refund id.

        `amount_cents=None` means the full amount. Never called
        automatically — a downgrade produces a credit against the next
        invoice, and turning that into money leaving the company is a
        deliberate, separately authorized action.
        """
        ...

    async def get_subscription_state(
        self, *, provider_subscription_id: str
    ) -> ProviderSubscriptionState | None: ...

    def verify_webhook(self, *, payload: bytes, signature: str) -> ProviderEvent | None:
        """Verify and translate, or raise.

        Synchronous because it is pure CPU — an HMAC over the body — with
        no network call, so making it async would add an await for
        nothing.

        Returns `None` for a verified event this system does not act on,
        which the caller acknowledges rather than treats as a failure.
        Raises `WebhookVerificationError` when the signature does not
        check out; that payload is never parsed, let alone acted on.
        """
        ...


class WebhookVerificationError(Exception):
    """The signature did not verify. Maps to HTTP 400.

    Never 401/403: those imply an identity that could be corrected. A bad
    signature means the payload is not from the provider at all, and the
    only correct response is to discard it without parsing.

    The message deliberately carries no detail about *why* it failed —
    telling a forger whether the timestamp or the digest was wrong helps
    them iterate.
    """

    def __init__(self) -> None:
        super().__init__("Webhook signature verification failed")
