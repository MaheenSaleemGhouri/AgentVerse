"""Request/response schemas for the money-moving billing surface."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from agentverse_api.billing_service.application.billing_actions_service import PlanChangeQuote
from agentverse_api.billing_service.domain.payment_provider import (
    ProviderInvoice,
    ProviderPaymentMethod,
)
from agentverse_api.billing_service.domain.plan import BillingInterval, PlanTier


class CheckoutRequest(BaseModel):
    plan_slug: PlanTier
    interval: BillingInterval = BillingInterval.MONTHLY
    #: Optional promotion code the customer already holds. Validated by
    #: the provider, not here — this system does not own the coupon
    #: catalog, and a local allowlist would be a second source of truth
    #: that could accept a code the provider rejects at the last step.
    coupon_code: str | None = Field(default=None, max_length=64)


class CheckoutResponse(BaseModel):
    """A URL to redirect the browser to.

    No subscription exists yet at this point, deliberately: it is created
    when the provider confirms payment. A client that treats this
    response as "subscribed" is wrong, which is why the field is named
    for what it is.
    """

    checkout_url: str
    session_id: str


class PortalResponse(BaseModel):
    portal_url: str


class CancelRequest(BaseModel):
    #: Default `true`: the customer has paid for the current period and
    #: keeps it. Immediate cancellation is available but is not the
    #: default, because it silently forfeits paid-for time.
    at_period_end: bool = True
    reason: str | None = Field(default=None, max_length=280)


class PlanChangeRequest(BaseModel):
    plan_slug: PlanTier
    interval: BillingInterval = BillingInterval.MONTHLY


class ProrationResponse(BaseModel):
    """Both halves separately, never one net figure.

    `saas-strategist`'s standard: an invoice itemizes the credit and the
    charge, because a single number cannot be decomposed back into
    "credit for unused Pro time" and "prorated Team charge", which is
    what a customer actually needs to check the maths.
    """

    unused_credit_cents: int
    prorated_charge_cents: int
    net_cents: int
    remaining_fraction_ppm: int


class PlanChangeQuoteResponse(BaseModel):
    from_plan: str
    to_plan: str
    interval: str
    is_upgrade: bool
    proration: ProrationResponse


class InvoiceResponse(BaseModel):
    id: str
    number: str | None
    status: str
    amount_due_cents: int
    amount_paid_cents: int
    currency: str
    created_at: datetime
    period_start: datetime | None
    period_end: datetime | None
    #: Provider-hosted and short-lived. Never proxied through this
    #: service: re-serving invoice PDFs would put them through
    #: infrastructure with no reason to hold them.
    hosted_invoice_url: str | None
    invoice_pdf_url: str | None


class InvoiceListResponse(BaseModel):
    data: list[InvoiceResponse]


class PaymentMethodResponse(BaseModel):
    """The non-sensitive remainder of a card.

    Brand, last four and expiry — read from the provider per request and
    never stored. There is no field here, or in any table, that a PAN or
    CVC could live in.
    """

    id: str
    brand: str | None
    last4: str | None
    exp_month: int | None
    exp_year: int | None
    is_default: bool


class PaymentMethodListResponse(BaseModel):
    data: list[PaymentMethodResponse]


class RefundRequest(BaseModel):
    invoice_id: str = Field(min_length=1, max_length=128)
    #: `null` refunds the full amount. Integer cents (Rule 15).
    amount_cents: int | None = Field(default=None, ge=1)
    reason: str | None = Field(default=None, max_length=280)


class RefundResponse(BaseModel):
    refund_id: str


class WebhookAckResponse(BaseModel):
    """Acknowledgement, not a result.

    Returned 200 for a duplicate and for an ignored event as well as a
    processed one: all three mean "do not retry this". A non-2xx would
    make the provider redeliver an event that was handled correctly.
    """

    outcome: str


def to_invoice_response(invoice: ProviderInvoice) -> InvoiceResponse:
    return InvoiceResponse(
        id=invoice.id,
        number=invoice.number,
        status=invoice.status,
        amount_due_cents=invoice.amount_due_cents,
        amount_paid_cents=invoice.amount_paid_cents,
        currency=invoice.currency,
        created_at=invoice.created_at,
        period_start=invoice.period_start,
        period_end=invoice.period_end,
        hosted_invoice_url=invoice.hosted_invoice_url,
        invoice_pdf_url=invoice.invoice_pdf_url,
    )


def to_payment_method_response(method: ProviderPaymentMethod) -> PaymentMethodResponse:
    return PaymentMethodResponse(
        id=method.id,
        brand=method.brand,
        last4=method.last4,
        exp_month=method.exp_month,
        exp_year=method.exp_year,
        is_default=method.is_default,
    )


def to_quote_response(quote: PlanChangeQuote) -> PlanChangeQuoteResponse:
    return PlanChangeQuoteResponse(
        from_plan=quote.from_plan.value,
        to_plan=quote.to_plan.value,
        interval=quote.interval.value,
        is_upgrade=quote.is_upgrade,
        proration=ProrationResponse(
            unused_credit_cents=quote.proration.unused_credit_cents,
            prorated_charge_cents=quote.proration.prorated_charge_cents,
            net_cents=quote.proration.net_cents,
            remaining_fraction_ppm=quote.proration.remaining_fraction_ppm,
        ),
    )
