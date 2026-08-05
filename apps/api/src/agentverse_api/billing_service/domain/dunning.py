"""The dunning clock: what happens, and when, after a payment fails.

`saas-strategist` sets the cadence — touchpoints at day 0, 3, 7 and 14 —
and this module makes it computable. It decides *when* to act and *what*
the action is; sending the actual email is the notification service's job
(M7), and charging the card again is the payment provider's (M3).

The clock runs from the **first** failure, not the most recent one. A
card that fails on day 0, day 3 and day 7 is one dunning cycle with three
touchpoints, not three cycles that each reset a two-week runway — that
reset is how a subscription ends up sitting in `past_due` forever, which
`billing-expert` names explicitly as a thing not to let happen.

Everything here is a pure function of `(first_failure_at, now)`. No
state of its own, no scheduler, no I/O: the retry job asks "what is due
for this subscription right now" and gets a deterministic answer it can
re-ask after a crash without double-acting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class DunningAction(StrEnum):
    """What the dunning runner should do at a touchpoint.

    `RETRY_PAYMENT` and `NOTIFY` are separate because they fail
    independently: a retry can succeed while the notification provider is
    down, and neither outcome should block the other.
    """

    NOTIFY = "notify"
    RETRY_PAYMENT = "retry_payment"
    CANCEL = "cancel"


@dataclass(frozen=True, slots=True)
class DunningStep:
    day: int
    action: DunningAction
    description: str


#: The schedule, in days since the first failed payment.
#:
#: Day 14 is terminal by design: `past_due` is a *time-bounded* state
#: (`billing-expert`, "don't let a subscription sit in past_due
#: indefinitely"). Two weeks is long enough to replace a card and short
#: enough that the platform is not indefinitely serving unpaid compute —
#: which, for an AI product where a run costs real provider money, is a
#: sharper cost than it would be for a seat-based SaaS.
DUNNING_SCHEDULE: tuple[DunningStep, ...] = (
    DunningStep(
        day=0,
        action=DunningAction.NOTIFY,
        description="Payment failed — card may need updating",
    ),
    DunningStep(day=3, action=DunningAction.RETRY_PAYMENT, description="First retry"),
    DunningStep(day=7, action=DunningAction.RETRY_PAYMENT, description="Second retry"),
    DunningStep(
        day=14,
        action=DunningAction.CANCEL,
        description="Dunning exhausted — subscription cancels",
    ),
)

#: How long a subscription may remain `past_due` before it is canceled.
DUNNING_WINDOW_DAYS: int = DUNNING_SCHEDULE[-1].day


def _elapsed_days(*, first_failure_at: datetime, now: datetime) -> int:
    """Whole days elapsed, floored, never negative.

    Floored rather than rounded so a touchpoint never fires early: a
    subscription 2.9 days into dunning is on day 2, and the day-3 retry
    waits. Firing a retry a few hours early would charge a card before
    the customer's own bank retry window has passed, which is how a
    single failure becomes two.
    """
    elapsed = now - first_failure_at
    if elapsed < timedelta(0):
        return 0
    return elapsed.days


def due_step(*, first_failure_at: datetime, now: datetime) -> DunningStep | None:
    """The furthest step whose day has arrived, or `None` before day 0.

    Returns the *furthest* rather than the next-unrun step so a runner
    that was down for a week does not walk the customer through three
    days of catch-up emails on resume. If day 14 has passed, the answer
    is cancel — the retries it slept through are no longer worth sending.

    Idempotency is the caller's, not this function's: it answers "what is
    due", and the caller records that it acted (via the subscription
    event log's idempotency key) so asking twice in the same day acts
    once.
    """
    elapsed = _elapsed_days(first_failure_at=first_failure_at, now=now)
    due: DunningStep | None = None
    for step in DUNNING_SCHEDULE:
        if elapsed >= step.day:
            due = step
    return due


def is_exhausted(*, first_failure_at: datetime, now: datetime) -> bool:
    """Has the window closed? The trigger for involuntary cancellation."""
    return _elapsed_days(first_failure_at=first_failure_at, now=now) >= DUNNING_WINDOW_DAYS


def deadline(first_failure_at: datetime) -> datetime:
    """When this subscription cancels if nothing recovers it.

    Shown to the customer in-product and in the dunning emails — a date
    is far more actionable than "your account may be suspended soon".
    """
    return first_failure_at + timedelta(days=DUNNING_WINDOW_DAYS)
