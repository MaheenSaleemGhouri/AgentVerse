"""The workspace's identity at the payment processor.

Kept as its own entity rather than columns on the subscription because
the two have genuinely different lifetimes: a workspace has one customer
record forever — it survives cancellation, and a returning customer
reuses it so their saved cards and invoice history come back with them —
while subscriptions come and go.

`provider` is stored explicitly even though Stripe is the only value
today. It is one TEXT column, and without it "which processor is this
ID from" is answerable only by knowing what year the row was written —
the kind of thing that is free to add now and a data migration later.
Nothing here imports or knows anything about Stripe's API; that lives
behind the provider port in M3.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class PaymentProvider(StrEnum):
    STRIPE = "stripe"


@dataclass(frozen=True, slots=True)
class BillingCustomer:
    """One workspace's payment-processor account.

    Holds no card data, no billing address, no tax ID — only the
    processor's opaque identifier. Everything sensitive stays with the
    processor, which is what keeps this platform out of PCI scope
    (`stripe-integration-expert`'s standing constraint) and means a dump
    of this table reveals nothing chargeable.
    """

    id: str
    workspace_id: str
    provider: PaymentProvider
    provider_customer_id: str
    billing_email: str | None
    created_at: datetime
    updated_at: datetime
