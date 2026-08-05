"""The subscription lifecycle: states, the transitions between them, and
what each state means for entitlement.

Pure — no I/O, no framework, no database. The whole state machine is one
table of `(state, trigger) -> state` triples, and every transition goes
through `apply`, which validates the current state first. That shape is
deliberate: `billing-expert`'s review checklist asks whether transitions
validate current state "rather than blindly overwriting `status`", and
the only way to guarantee that across a growing number of call sites is
to make the bare overwrite unavailable.

Two modelling decisions carry most of the weight here.

**"Scheduled to cancel" is a flag, not a state.** A customer who clicks
cancel on day 3 of a paid month has paid for the rest of that month. If
that made the subscription `canceled`, entitlement would collapse to
Free immediately and we would have taken money for service we then
refused. So it stays `ACTIVE` with `cancel_at_period_end` set, and the
terminal transition happens when the period actually ends.

**`PAST_DUE` keeps full entitlement.** Dunning exists precisely because
a failed payment is usually a expired card, not a decision to leave.
Cutting service off at the first failed charge converts a recoverable
billing problem into churn. Entitlement collapses when dunning is
exhausted and the subscription reaches `CANCELED`, which is a bounded,
scheduled outcome rather than an indefinite grace period.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from agentverse_api.billing_service.domain.plan import BillingInterval, PlanTier


class SubscriptionStatus(StrEnum):
    """Where a subscription is in its life.

    Deliberately *not* a state per commercial nuance — there is no
    `canceling`, no `expiring`, no `grace`. Each of those is an existing
    state plus a date, and modelling them as states would multiply the
    transition table without making any entitlement decision different.
    """

    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    PAUSED = "paused"
    CANCELED = "canceled"


#: Statuses under which the workspace gets its subscribed plan's
#: entitlements rather than falling back to Free.
#:
#: `PAUSED` is excluded on purpose: pausing is the customer asking to
#: stop paying for a while, and continuing to serve the paid plan's
#: limits would make pause strictly better than an active subscription.
_ENTITLING_STATUSES: frozenset[SubscriptionStatus] = frozenset(
    {
        SubscriptionStatus.TRIALING,
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.PAST_DUE,
    }
)

#: Statuses from which a subscription can still move somewhere else.
#: `CANCELED` is terminal — recovering a canceled customer creates a new
#: subscription row, so the old one's history stays immutable and
#: "when did this subscription end" has exactly one answer.
_TERMINAL_STATUSES: frozenset[SubscriptionStatus] = frozenset({SubscriptionStatus.CANCELED})


class SubscriptionTrigger(StrEnum):
    """What causes a transition.

    Every trigger is either a verified payment-processor event or an
    explicit authenticated action — never an inference from client state
    (`billing-expert` operating principle 1). The name says which:
    `PAYMENT_*` and `TRIAL_EXPIRED` arrive from the processor or a
    scheduled job; `CUSTOMER_*` are deliberate user actions.
    """

    TRIAL_STARTED = "trial_started"
    TRIAL_EXPIRED = "trial_expired"
    PAYMENT_SUCCEEDED = "payment_succeeded"
    PAYMENT_FAILED = "payment_failed"
    DUNNING_EXHAUSTED = "dunning_exhausted"
    CUSTOMER_PAUSED = "customer_paused"
    CUSTOMER_RESUMED = "customer_resumed"
    CUSTOMER_CANCELED = "customer_canceled"
    PERIOD_ENDED_AFTER_CANCEL = "period_ended_after_cancel"
    PLAN_CHANGED = "plan_changed"


#: The entire state machine. A `(status, trigger)` pair absent from this
#: mapping is not a transition — `apply` refuses it rather than guessing.
#:
#: Same-state entries are real transitions, not no-ops: a plan change on
#: an active subscription leaves the status alone but must still be
#: recorded, and routing it through this table means it cannot skip the
#: event log.
_TRANSITIONS: dict[tuple[SubscriptionStatus, SubscriptionTrigger], SubscriptionStatus] = {
    # A trial can convert, lapse, or be abandoned.
    (SubscriptionStatus.TRIALING, SubscriptionTrigger.PAYMENT_SUCCEEDED): (
        SubscriptionStatus.ACTIVE
    ),
    (SubscriptionStatus.TRIALING, SubscriptionTrigger.TRIAL_EXPIRED): SubscriptionStatus.CANCELED,
    # A card can fail on the very first charge at the end of a trial.
    (SubscriptionStatus.TRIALING, SubscriptionTrigger.PAYMENT_FAILED): (
        SubscriptionStatus.PAST_DUE
    ),
    (SubscriptionStatus.TRIALING, SubscriptionTrigger.CUSTOMER_CANCELED): (
        SubscriptionStatus.CANCELED
    ),
    (SubscriptionStatus.TRIALING, SubscriptionTrigger.PLAN_CHANGED): SubscriptionStatus.TRIALING,
    # Renewals keep an active subscription active; that event still has
    # to be logged, which is why it is a transition rather than nothing.
    (SubscriptionStatus.ACTIVE, SubscriptionTrigger.PAYMENT_SUCCEEDED): SubscriptionStatus.ACTIVE,
    (SubscriptionStatus.ACTIVE, SubscriptionTrigger.PAYMENT_FAILED): SubscriptionStatus.PAST_DUE,
    (SubscriptionStatus.ACTIVE, SubscriptionTrigger.CUSTOMER_PAUSED): SubscriptionStatus.PAUSED,
    (SubscriptionStatus.ACTIVE, SubscriptionTrigger.CUSTOMER_CANCELED): (
        SubscriptionStatus.CANCELED
    ),
    (SubscriptionStatus.ACTIVE, SubscriptionTrigger.PERIOD_ENDED_AFTER_CANCEL): (
        SubscriptionStatus.CANCELED
    ),
    (SubscriptionStatus.ACTIVE, SubscriptionTrigger.PLAN_CHANGED): SubscriptionStatus.ACTIVE,
    # Dunning: recovery returns to active, exhaustion is involuntary
    # churn. A customer can also cancel outright while past due.
    (SubscriptionStatus.PAST_DUE, SubscriptionTrigger.PAYMENT_SUCCEEDED): (
        SubscriptionStatus.ACTIVE
    ),
    # A second failure while already past due restarts nothing — the
    # dunning clock runs from the *first* failure, so this is a
    # same-state transition kept only for the audit trail.
    (SubscriptionStatus.PAST_DUE, SubscriptionTrigger.PAYMENT_FAILED): (
        SubscriptionStatus.PAST_DUE
    ),
    (SubscriptionStatus.PAST_DUE, SubscriptionTrigger.DUNNING_EXHAUSTED): (
        SubscriptionStatus.CANCELED
    ),
    (SubscriptionStatus.PAST_DUE, SubscriptionTrigger.CUSTOMER_CANCELED): (
        SubscriptionStatus.CANCELED
    ),
    # A paused subscription resumes or ends. It is deliberately not
    # payable: no PAYMENT_* trigger applies, because nothing should be
    # charging a paused customer in the first place.
    (SubscriptionStatus.PAUSED, SubscriptionTrigger.CUSTOMER_RESUMED): SubscriptionStatus.ACTIVE,
    (SubscriptionStatus.PAUSED, SubscriptionTrigger.CUSTOMER_CANCELED): (
        SubscriptionStatus.CANCELED
    ),
}


class InvalidTransitionError(Exception):
    """The trigger does not apply to the current status. Maps to HTTP 409.

    A conflict rather than a 400: the request was well-formed, and would
    have been valid against a different current state. Telling a caller
    "you cannot resume a subscription that is not paused" is a statement
    about the resource, not about their input.
    """

    def __init__(self, *, status: SubscriptionStatus, trigger: SubscriptionTrigger) -> None:
        self.status = status
        self.trigger = trigger
        super().__init__(f"Cannot apply {trigger.value!r} to a subscription in {status.value!r}")


def apply(*, status: SubscriptionStatus, trigger: SubscriptionTrigger) -> SubscriptionStatus:
    """The resulting status, or raise. The only way status changes."""
    try:
        return _TRANSITIONS[(status, trigger)]
    except KeyError as exc:
        raise InvalidTransitionError(status=status, trigger=trigger) from exc


def can_apply(*, status: SubscriptionStatus, trigger: SubscriptionTrigger) -> bool:
    return (status, trigger) in _TRANSITIONS


def is_terminal(status: SubscriptionStatus) -> bool:
    return status in _TERMINAL_STATUSES


def entitles(status: SubscriptionStatus) -> bool:
    """Does this status grant the subscribed plan's limits?

    Read by the entitlement resolver on every quota check, which is why
    it lives here as one function over the status rather than as a
    condition spelled out at each call site.
    """
    return status in _ENTITLING_STATUSES


@dataclass(frozen=True, slots=True)
class Subscription:
    """One workspace's subscription, as the rest of the system sees it.

    Frozen: a transition produces a new value rather than mutating this
    one, so a caller cannot half-apply a change and leave the object
    describing a state the database never saw.

    `plan_slug` rather than a full `Plan`: the plan is catalog data that
    changes independently (a price edit must not require rewriting every
    subscription row), and the resolver joins them at read time.
    """

    id: str
    workspace_id: str
    plan_id: str
    plan_slug: PlanTier
    status: SubscriptionStatus
    interval: BillingInterval
    current_period_start: datetime
    current_period_end: datetime
    trial_end: datetime | None
    cancel_at_period_end: bool
    canceled_at: datetime | None
    past_due_since: datetime | None
    provider_subscription_id: str | None
    created_at: datetime
    updated_at: datetime

    @property
    def entitles(self) -> bool:
        return entitles(self.status)

    @property
    def is_terminal(self) -> bool:
        return is_terminal(self.status)

    def in_trial_at(self, moment: datetime) -> bool:
        """Trial membership is decided by the clock, not by the status
        alone — a subscription can still read `TRIALING` for the seconds
        between the trial ending and the job that converts it running.
        """
        if self.trial_end is None:
            return False
        return moment < self.trial_end
