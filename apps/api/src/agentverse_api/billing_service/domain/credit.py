"""Account credit: a workspace's balance, and the arithmetic that moves
it.

Pure integer cents (Rule 15). Credit is real money owed *to* the
customer — a refund that stayed on account, a referral reward, a
goodwill grant — so every rule here exists to make a balance defensible
rather than merely plausible.

**The ledger is the truth; the balance is a projection.** Every movement
is an append-only transaction row, and the balance column is the fast
read derived from them. That is not redundancy: a bare balance answers
"how much" and nothing else, and the first time a customer asks "why is
this $40 and not $50" a system without a ledger has no answer at all.
`reconcile` re-derives the balance from the ledger and is expected to
agree exactly.

**Credit can never go negative.** A negative balance would mean the
platform is owed money through a mechanism that has no way to collect
it — that is what an invoice is for. Over-consuming is refused, not
recorded.

**Applying credit never reduces an amount below zero.** A $50 credit
against a $20 invoice consumes $20 and leaves $30 on the account; it
does not produce a -$30 invoice, which no payment provider can charge
and no customer can be paid from.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class CreditReason(StrEnum):
    """Why a credit movement happened.

    Recorded per transaction because "your balance went down by $12" is
    not an answer a customer can act on, and because the difference
    between a promotional grant and a refund matters for revenue
    reporting — `saas-strategist` counts them differently.
    """

    REFERRAL_REWARD = "referral_reward"
    COUPON_REDEMPTION = "coupon_redemption"
    PROMOTIONAL_GRANT = "promotional_grant"
    REFUND_TO_ACCOUNT = "refund_to_account"
    SUPPORT_ADJUSTMENT = "support_adjustment"
    INVOICE_APPLIED = "invoice_applied"
    EXPIRED = "expired"


#: Reasons that move the balance up. Everything else moves it down.
#:
#: Declared rather than inferred from the sign of an amount: an amount's
#: sign is easy to get backwards at a call site, and a credit applied
#: with the wrong sign is money invented from nothing.
_CREDITING: frozenset[CreditReason] = frozenset(
    {
        CreditReason.REFERRAL_REWARD,
        CreditReason.COUPON_REDEMPTION,
        CreditReason.PROMOTIONAL_GRANT,
        CreditReason.REFUND_TO_ACCOUNT,
        CreditReason.SUPPORT_ADJUSTMENT,
    }
)


def is_credit(reason: CreditReason) -> bool:
    return reason in _CREDITING


class InsufficientCreditError(Exception):
    """More credit was consumed than the workspace holds. Maps to 409.

    Refused rather than allowed to go negative: a negative balance means
    the platform is owed money through a mechanism with no way to
    collect it.
    """

    def __init__(self, *, balance_cents: int, requested_cents: int) -> None:
        self.balance_cents = balance_cents
        self.requested_cents = requested_cents
        super().__init__(
            f"Workspace holds {balance_cents} credit cents; {requested_cents} were requested"
        )


class InvalidCreditAmountError(ValueError):
    """A zero or negative movement.

    Zero is refused too. A ledger row that moves nothing is noise in the
    one record a customer reads to understand their balance, and every
    caller that would write one has a bug — an empty coupon, a
    zero-value reward — worth surfacing rather than recording.
    """


@dataclass(frozen=True, slots=True)
class CreditTransaction:
    """One movement, as the rest of the system sees it.

    `amount_cents` is always a positive magnitude; `reason` decides the
    direction. Storing a signed amount would make "did this add or
    subtract" depend on reading the sign correctly at every call site,
    and the sign is exactly the thing that is easy to get backwards.
    """

    id: str
    workspace_id: str
    reason: CreditReason
    amount_cents: int
    #: Balance immediately after this movement. Denormalized on purpose:
    #: it is what makes a statement readable line by line, and it turns
    #: a corrupted ledger into something a reader notices rather than
    #: something only a full recomputation reveals.
    balance_after_cents: int
    description: str
    #: The thing that caused it — a referral id, a coupon code, an
    #: invoice id. Free text because the causes come from four different
    #: tables and a nullable FK per cause reads worse than one string.
    source_ref: str | None
    #: When a promotional grant stops being spendable. `None` means it
    #: never expires, which is the right default for a refund: money the
    #: customer already paid should not evaporate.
    expires_at: datetime | None
    created_at: datetime

    @property
    def signed_cents(self) -> int:
        return self.amount_cents if is_credit(self.reason) else -self.amount_cents


@dataclass(frozen=True, slots=True)
class CreditApplication:
    """The result of applying credit to an amount owed."""

    applied_cents: int
    remaining_due_cents: int
    remaining_balance_cents: int


def apply_credit(*, balance_cents: int, amount_due_cents: int) -> CreditApplication:
    """Spend as much credit as the amount owed can absorb.

    Never produces a negative invoice: a $50 balance against a $20
    invoice consumes $20 and leaves $30, because no payment provider can
    charge -$30 and no customer can be paid from it.

    A zero or negative `amount_due_cents` consumes nothing — a credit
    note or a fully discounted period has nothing for credit to reduce.
    """
    if balance_cents < 0:
        raise InvalidCreditAmountError(f"balance must not be negative, got {balance_cents}")
    if amount_due_cents <= 0:
        return CreditApplication(
            applied_cents=0,
            remaining_due_cents=max(0, amount_due_cents),
            remaining_balance_cents=balance_cents,
        )
    applied = min(balance_cents, amount_due_cents)
    return CreditApplication(
        applied_cents=applied,
        remaining_due_cents=amount_due_cents - applied,
        remaining_balance_cents=balance_cents - applied,
    )


def next_balance(*, balance_cents: int, reason: CreditReason, amount_cents: int) -> int:
    """The balance after one movement, or raise.

    The single place a balance changes. Every guard that keeps a balance
    defensible — positive amounts only, never negative afterwards —
    lives here rather than at the call sites, because a call site that
    forgets one is the bug this function exists to make impossible.
    """
    if amount_cents <= 0:
        raise InvalidCreditAmountError(
            f"a credit movement must be a positive amount, got {amount_cents}"
        )
    if balance_cents < 0:
        raise InvalidCreditAmountError(f"balance must not already be negative, got {balance_cents}")
    if is_credit(reason):
        return balance_cents + amount_cents
    if amount_cents > balance_cents:
        raise InsufficientCreditError(balance_cents=balance_cents, requested_cents=amount_cents)
    return balance_cents - amount_cents


def expired_amount(*, transactions: list[CreditTransaction], now: datetime) -> int:
    """How much unspent promotional credit has passed its expiry.

    Computed from the granting rows rather than tracked as a countdown:
    a countdown has to be decremented correctly by every spend, and
    getting that wrong silently expires credit a customer still holds.

    Deliberately approximate in one respect, and it is the safe
    direction: spends are not attributed to specific grants, so this
    treats every expired grant as unspent. The caller nets the result
    against the live balance, which means the platform can never expire
    more than the customer actually holds.
    """
    return sum(
        transaction.amount_cents
        for transaction in transactions
        if is_credit(transaction.reason)
        and transaction.expires_at is not None
        and transaction.expires_at <= now
    )
