"""Proration for mid-cycle plan changes.

Pure integer arithmetic over exact timestamps. Three properties this
module is built to guarantee, each because getting it wrong costs real
money in a way a customer notices:

**Exact, not approximate.** Time is measured in whole seconds against
the real period boundaries, never in "months" or "days remaining"
rounded to a calendar unit. A 28-day February and a 31-day March are
different amounts of service, and a customer who upgrades on the 15th of
each pays differently and correctly.

**Deterministic and idempotent.** The same inputs always produce the
same cents. There is no `now()` inside — the moment of change is passed
in — so recomputing a proration for the same plan-change event a week
later, from the stored timestamps, reproduces the original number
exactly. That is what makes the reconciliation query in `billing-expert`'s
Definition of Done able to prove an invoice line was right.

**Rounding never favors us.** Integer division has to drop a fraction of
a cent somewhere. The credit for unused time rounds *up* and the charge
for new service rounds *down*, so the residual cent always lands with
the customer. It costs at most two cents per plan change and removes an
entire class of "you overcharged me by a penny" support ticket. The
alternative conventions (floor both, round-half-up) are defensible too;
what is not defensible is leaving it unstated and inconsistent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class InvalidBillingPeriodError(ValueError):
    """The period boundaries or the change moment are not coherent.

    Raised rather than clamped. A change timestamp outside its own
    billing period means an upstream bug — a clock skew, a stale period
    row, a replayed event against the wrong period — and silently
    clamping it to the boundary would turn that bug into a plausible
    invoice nobody ever questions.
    """


@dataclass(frozen=True, slots=True)
class Proration:
    """The two halves of a mid-cycle plan change, in integer cents.

    Kept as two signed-by-name fields rather than one net number because
    the invoice has to show them separately — "Credit for unused Pro
    time" and "Prorated Team charge" are the line items
    `saas-strategist`'s Design Standards require, and a single net figure
    cannot be decomposed back into them.

    Both are non-negative magnitudes; `net_cents` applies the sign.
    """

    unused_credit_cents: int
    prorated_charge_cents: int
    remaining_seconds: int
    period_seconds: int

    @property
    def net_cents(self) -> int:
        """Positive means the customer owes; negative means they are owed.

        A downgrade mid-cycle routinely produces a negative net, which is
        a credit against the next invoice rather than a refund — refunds
        are a separate, deliberate action (M3), never an automatic
        consequence of arithmetic.
        """
        return self.prorated_charge_cents - self.unused_credit_cents

    @property
    def remaining_fraction_ppm(self) -> int:
        """Unused share of the period in parts per million.

        Exposed for the invoice's explanatory line ("18 of 30 days
        remaining") and for tests that assert the split without
        re-deriving it. Parts-per-million rather than a float because
        nothing in this module is allowed to be a float, including the
        numbers that only get displayed.
        """
        if self.period_seconds == 0:
            return 0
        return (self.remaining_seconds * 1_000_000) // self.period_seconds


def _validate(
    *, period_start: datetime, period_end: datetime, change_at: datetime
) -> tuple[int, int]:
    if period_end <= period_start:
        raise InvalidBillingPeriodError(
            f"period_end ({period_end.isoformat()}) must be after "
            f"period_start ({period_start.isoformat()})"
        )
    if change_at < period_start or change_at > period_end:
        raise InvalidBillingPeriodError(
            f"change_at ({change_at.isoformat()}) falls outside its billing period "
            f"{period_start.isoformat()}..{period_end.isoformat()}"
        )
    period_seconds = int((period_end - period_start).total_seconds())
    remaining_seconds = int((period_end - change_at).total_seconds())
    return period_seconds, remaining_seconds


def _ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)


def prorate(
    *,
    old_price_cents: int,
    new_price_cents: int,
    period_start: datetime,
    period_end: datetime,
    change_at: datetime,
) -> Proration:
    """Credit the unused remainder of the old plan, charge the same
    remainder on the new one.

    Both prices are the *full period* price for their plan at the
    subscription's billing interval — passing an annual price with a
    monthly period would produce a confidently wrong number, so callers
    resolve the price through `plan.price_cents(plan, interval)` rather
    than reaching for a field.

    A change exactly at `period_start` prorates the whole period; one
    exactly at `period_end` prorates nothing. Both are handled by the
    arithmetic rather than special-cased, which is why they are worth
    asserting in tests.
    """
    if old_price_cents < 0 or new_price_cents < 0:
        raise ValueError(
            f"prices must not be negative, got old={old_price_cents} new={new_price_cents}"
        )
    period_seconds, remaining_seconds = _validate(
        period_start=period_start, period_end=period_end, change_at=change_at
    )
    # Credit rounds up, charge rounds down — the residual sub-cent always
    # lands in the customer's favor. See the module docstring.
    credit = _ceil_div(old_price_cents * remaining_seconds, period_seconds)
    charge = (new_price_cents * remaining_seconds) // period_seconds
    return Proration(
        unused_credit_cents=credit,
        prorated_charge_cents=charge,
        remaining_seconds=remaining_seconds,
        period_seconds=period_seconds,
    )
