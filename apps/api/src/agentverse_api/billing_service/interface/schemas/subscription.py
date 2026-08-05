"""Response schemas for the subscription surface."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from agentverse_api.billing_service.domain import dunning
from agentverse_api.billing_service.domain.subscription import Subscription


class DunningStatusResponse(BaseModel):
    """Where a past-due subscription is in its recovery window.

    Present only while past due. `deadline` is the date the subscription
    cancels if nothing recovers it — a concrete date, because "your
    account may be suspended soon" gives a customer nothing to act on.
    """

    since: datetime
    deadline: datetime
    days_remaining: int
    next_action: str


class SubscriptionResponse(BaseModel):
    id: str
    workspace_id: str
    plan_slug: str
    status: str
    billing_interval: str
    current_period_start: datetime
    current_period_end: datetime
    trial_end: datetime | None
    #: `true` means the subscription is still fully active and entitled,
    #: and will end at `current_period_end` rather than now. The UI must
    #: say so — a customer who cancels and immediately sees "active" with
    #: no end date reads it as the cancellation having failed.
    cancel_at_period_end: bool
    canceled_at: datetime | None
    #: Whether this status grants the plan's limits. Sent explicitly
    #: rather than left for the client to derive from `status`, so the
    #: rule that `past_due` still entitles lives in one place — the
    #: server — instead of being reimplemented in every consumer.
    entitles: bool
    dunning: DunningStatusResponse | None


class SubscriptionEventResponse(BaseModel):
    trigger: str
    from_status: str
    to_status: str
    actor: str
    occurred_at: datetime


class SubscriptionHistoryResponse(BaseModel):
    data: list[SubscriptionEventResponse]


def to_subscription_response(subscription: Subscription, *, now: datetime) -> SubscriptionResponse:
    dunning_status: DunningStatusResponse | None = None
    if subscription.past_due_since is not None:
        deadline = dunning.deadline(subscription.past_due_since)
        step = dunning.due_step(first_failure_at=subscription.past_due_since, now=now)
        dunning_status = DunningStatusResponse(
            since=subscription.past_due_since,
            deadline=deadline,
            # Floored at zero: a negative countdown after the window has
            # closed but before the sweep has run would render as
            # "-2 days remaining".
            days_remaining=max(0, (deadline - now).days),
            next_action=step.action.value if step is not None else dunning.DunningAction.NOTIFY,
        )
    return SubscriptionResponse(
        id=subscription.id,
        workspace_id=subscription.workspace_id,
        plan_slug=subscription.plan_slug.value,
        status=subscription.status.value,
        billing_interval=subscription.interval.value,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        trial_end=subscription.trial_end,
        cancel_at_period_end=subscription.cancel_at_period_end,
        canceled_at=subscription.canceled_at,
        entitles=subscription.entitles,
        dunning=dunning_status,
    )
