"""The billing context's view of notifications.

A thin translation layer, and the reason it exists rather than the
billing services calling `NotificationService` directly is the dedupe
key. Every billing notification needs one derived from the event that
caused it, and letting six call sites each invent their own is how two
of them end up producing a key containing `now()` — which silently turns
deduplication off for exactly the messages that most need it.

So the keys are built here, in one place, from the identifiers the
billing domain already has: a subscription id, a period start, a dunning
day. Each is stable under retry by construction.

Every method returns rather than raising. A billing transition that
succeeded must not be rolled back because a notification could not be
raised — see `NotificationService.raise_`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from agentverse_api.notification_service.application.notification_service import (
    NotificationService,
)
from agentverse_api.notification_service.domain import templates
from agentverse_api.notification_service.domain.notification import (
    Notification,
    NotificationKind,
    Severity,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BillingNotifier:
    notifications: NotificationService

    async def trial_ending(
        self,
        *,
        workspace_id: str,
        subscription_id: str,
        plan_name: str,
        ends_at: datetime,
        price_cents: int,
        recipient: str | None,
    ) -> Notification | None:
        return await self.notifications.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.TRIAL_ENDING,
            message=templates.trial_ending(
                workspace_id=workspace_id,
                plan_name=plan_name,
                ends_at=ends_at,
                price_cents=price_cents,
            ),
            # Keyed on the subscription, not the day: a reminder sweep
            # that runs daily through the last week of a trial would
            # otherwise send seven identical emails.
            dedupe_key=f"trial_ending:{subscription_id}",
            recipient=recipient,
        )

    async def payment_failed(
        self,
        *,
        workspace_id: str,
        subscription_id: str,
        amount_cents: int,
        deadline: datetime,
        recipient: str | None,
        first_failure_at: datetime,
    ) -> Notification | None:
        return await self.notifications.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.PAYMENT_FAILED,
            message=templates.payment_failed(
                workspace_id=workspace_id, amount_cents=amount_cents, deadline=deadline
            ),
            # Keyed on the dunning cycle's start, so every failure within
            # one cycle produces one "payment failed" message. Subsequent
            # touchpoints are `dunning_reminder`, which reads differently
            # on purpose.
            dedupe_key=f"payment_failed:{subscription_id}:{first_failure_at.isoformat()}",
            recipient=recipient,
        )

    async def dunning_reminder(
        self,
        *,
        workspace_id: str,
        subscription_id: str,
        first_failure_at: datetime,
        day: int,
        days_remaining: int,
        deadline: datetime,
        recipient: str | None,
    ) -> Notification | None:
        return await self.notifications.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.DUNNING_REMINDER,
            message=templates.dunning_reminder(
                workspace_id=workspace_id,
                days_remaining=days_remaining,
                deadline=deadline,
            ),
            # Keyed on the cycle *and* the touchpoint day, so the sweep
            # running twice on day 3 sends one email while the day-7
            # touchpoint still gets through.
            dedupe_key=f"dunning:{subscription_id}:{first_failure_at.isoformat()}:{day}",
            recipient=recipient,
        )

    async def subscription_canceled(
        self,
        *,
        workspace_id: str,
        subscription_id: str,
        plan_name: str,
        was_involuntary: bool,
        recipient: str | None,
    ) -> Notification | None:
        return await self.notifications.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.SUBSCRIPTION_CANCELED,
            message=templates.subscription_canceled(
                workspace_id=workspace_id,
                plan_name=plan_name,
                was_involuntary=was_involuntary,
            ),
            dedupe_key=f"canceled:{subscription_id}",
            recipient=recipient,
        )

    async def payment_succeeded(
        self,
        *,
        workspace_id: str,
        amount_cents: int,
        plan_name: str,
        provider_event_id: str,
    ) -> Notification | None:
        return await self.notifications.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.PAYMENT_SUCCEEDED,
            message=templates.payment_succeeded(
                workspace_id=workspace_id, amount_cents=amount_cents, plan_name=plan_name
            ),
            # The provider's own event id: a redelivered webhook
            # reproduces it exactly.
            dedupe_key=f"payment_succeeded:{provider_event_id}",
        )

    async def plan_changed(
        self,
        *,
        workspace_id: str,
        subscription_id: str,
        from_plan: str,
        to_plan: str,
        net_cents: int,
        changed_at: datetime,
    ) -> Notification | None:
        return await self.notifications.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.PLAN_CHANGED,
            message=templates.plan_changed(
                workspace_id=workspace_id,
                from_plan=from_plan,
                to_plan=to_plan,
                net_cents=net_cents,
            ),
            # Includes the moment because a workspace can legitimately
            # change plan twice — unlike a cancellation, which happens
            # once per subscription.
            dedupe_key=f"plan_changed:{subscription_id}:{changed_at.isoformat()}",
        )

    async def quota_threshold(
        self,
        *,
        workspace_id: str,
        dimension: str,
        percent: int,
        limit: int,
        period_start: datetime,
        recipient: str | None,
        exceeded: bool,
    ) -> Notification | None:
        """The 80% nudge and the hard stop, one method.

        Keyed on the billing period, so a customer gets one warning per
        period per dimension rather than one per run once they cross the
        line — which would be hundreds.
        """
        if exceeded:
            return await self.notifications.raise_(
                workspace_id=workspace_id,
                kind=NotificationKind.QUOTA_EXCEEDED,
                message=templates.quota_exceeded(
                    workspace_id=workspace_id, dimension=dimension, limit=limit
                ),
                dedupe_key=f"quota_exceeded:{workspace_id}:{dimension}:{period_start.isoformat()}",
                recipient=recipient,
                severity=Severity.CRITICAL,
            )
        return await self.notifications.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.QUOTA_APPROACHING,
            message=templates.quota_approaching(
                workspace_id=workspace_id,
                dimension=dimension,
                percent=percent,
                limit=limit,
            ),
            dedupe_key=f"quota_approaching:{workspace_id}:{dimension}:{period_start.isoformat()}",
        )

    async def credit_granted(
        self, *, workspace_id: str, amount_cents: int, reason: str, source_ref: str
    ) -> Notification | None:
        return await self.notifications.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.CREDIT_GRANTED,
            message=templates.credit_granted(
                workspace_id=workspace_id, amount_cents=amount_cents, reason=reason
            ),
            # The same key the credit grant itself used, so a replayed
            # grant that added no credit also raises no notification.
            dedupe_key=f"credit:{source_ref}",
        )

    async def referral_rewarded(
        self, *, workspace_id: str, amount_cents: int, referral_id: str, recipient: str | None
    ) -> Notification | None:
        return await self.notifications.raise_(
            workspace_id=workspace_id,
            kind=NotificationKind.REFERRAL_REWARDED,
            message=templates.referral_rewarded(
                workspace_id=workspace_id, amount_cents=amount_cents
            ),
            dedupe_key=f"referral:{referral_id}:{workspace_id}",
            recipient=recipient,
        )
