"""The words. Pure functions from facts to a rendered message.

Every template is a function over typed arguments rather than a string
with placeholders substituted at a call site. That is what makes a
missing value a type error instead of an email that says
"Your {plan} subscription" to a real customer.

**Copy rules applied here** (`copywriting-expert`, §15's microcopy
standard): direct, technically precise, no forced enthusiasm, and every
message ends in exactly one thing to do. A billing email that says "we
value your business" and gives no next step wastes the only attention
the customer will spend on it.

**Every claim is a fact the caller passed in.** No template invents a
date, an amount or a plan name. A dunning email quoting the wrong
deadline is worse than no email — it tells the customer they have time
they do not have.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from agentverse_api.notification_service.domain.notification import NotificationKind


@dataclass(frozen=True, slots=True)
class RenderedMessage:
    """One message, ready for both channels.

    `title`/`body` serve the in-app entry and `subject`/`email_body` the
    inbox, because the two read differently: an in-app title sits under
    a heading that already says "Notifications", while a subject line
    competes with everything else in a mailbox and has to name the
    product.
    """

    title: str
    body: str
    subject: str
    email_body: str
    action_path: str | None


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _date(moment: datetime) -> str:
    return moment.strftime("%-d %B %Y") if hasattr(moment, "strftime") else str(moment)


def _billing_path(workspace_id: str) -> str:
    return f"/dashboard/{workspace_id}/billing"


def trial_ending(
    *, workspace_id: str, plan_name: str, ends_at: datetime, price_cents: int
) -> RenderedMessage:
    """Sent before the first charge, not after it.

    The amount and the date are both stated: "your trial is ending" with
    neither is a message that makes a customer go and look, which is the
    work the email was supposed to save them.
    """
    return RenderedMessage(
        title=f"Your {plan_name} trial ends on {_date(ends_at)}",
        body=(
            f"We will charge {_money(price_cents)} on {_date(ends_at)} and your "
            f"{plan_name} plan continues. Cancel before then and you will not be charged."
        ),
        subject=f"Your AgentVerse {plan_name} trial ends {_date(ends_at)}",
        email_body=(
            f"Your {plan_name} trial ends on {_date(ends_at)}.\n\n"
            f"On that date we will charge {_money(price_cents)} and your plan continues "
            "with no interruption. If you would rather not continue, cancel before then "
            "and you will not be charged.\n\n"
            "Review your plan: {link}"
        ),
        action_path=_billing_path(workspace_id),
    )


def payment_failed(*, workspace_id: str, amount_cents: int, deadline: datetime) -> RenderedMessage:
    """The first dunning touchpoint.

    Leads with the deadline because that is the actionable fact. A
    customer who knows service stops on the 24th can decide; one told
    "there was a problem with your payment" cannot.
    """
    return RenderedMessage(
        title="We could not take your payment",
        body=(
            f"Your {_money(amount_cents)} payment did not go through. Your subscription "
            f"stays active until {_date(deadline)} — update your payment method before "
            "then to keep it running."
        ),
        subject="Action needed: your AgentVerse payment did not go through",
        email_body=(
            f"We tried to charge {_money(amount_cents)} and the payment did not go "
            "through. This is usually an expired card.\n\n"
            f"Nothing changes yet. Your subscription stays active until {_date(deadline)}, "
            "and we will retry automatically in the meantime. If we still cannot take "
            "payment by then, the subscription will be canceled.\n\n"
            "Update your payment method: {link}"
        ),
        action_path=_billing_path(workspace_id),
    )


def dunning_reminder(
    *, workspace_id: str, days_remaining: int, deadline: datetime
) -> RenderedMessage:
    """A later touchpoint in the same cycle.

    Distinct from `payment_failed` so the second and third messages do
    not read as the first one repeated — a customer who gets the
    identical email three times learns to ignore it.
    """
    urgency = "today" if days_remaining <= 1 else f"in {days_remaining} days"
    return RenderedMessage(
        title=f"Your subscription is canceled {urgency} unless payment succeeds",
        body=(
            f"We still cannot take payment. Your subscription is canceled on "
            f"{_date(deadline)} unless the payment method is updated."
        ),
        subject=f"Your AgentVerse subscription is canceled {urgency}",
        email_body=(
            "We have retried your payment and it is still not going through.\n\n"
            f"Your subscription is canceled on {_date(deadline)} unless we can take "
            "payment before then. Your agents keep running until that date.\n\n"
            "Update your payment method: {link}"
        ),
        action_path=_billing_path(workspace_id),
    )


def subscription_canceled(
    *, workspace_id: str, plan_name: str, was_involuntary: bool
) -> RenderedMessage:
    """Involuntary and voluntary cancellation read differently.

    A customer who chose to leave does not need to be told their payment
    failed, and one whose card expired should not receive a message
    thanking them for their decision.
    """
    if was_involuntary:
        return RenderedMessage(
            title=f"Your {plan_name} subscription has been canceled",
            body=(
                "We were not able to take payment within the retry window, so the "
                "subscription has ended. Your workspace is now on the Free plan and "
                "your data is intact."
            ),
            subject="Your AgentVerse subscription has been canceled",
            email_body=(
                f"We were not able to take payment for your {plan_name} subscription "
                "within the retry window, so it has been canceled.\n\n"
                "Nothing has been deleted. Your workspace is on the Free plan and all "
                "your agents, knowledge bases and history are intact — resubscribing "
                "restores your previous limits immediately.\n\n"
                "Resubscribe: {link}"
            ),
            action_path=_billing_path(workspace_id),
        )
    return RenderedMessage(
        title=f"Your {plan_name} subscription has ended",
        body=(
            "Your workspace is now on the Free plan. Everything you built is still "
            "here, and resubscribing restores your previous limits."
        ),
        subject="Your AgentVerse subscription has ended",
        email_body=(
            f"Your {plan_name} subscription has ended as requested.\n\n"
            "Your workspace is on the Free plan. Nothing has been deleted — your "
            "agents, knowledge bases and run history are all intact, and resubscribing "
            "restores your previous limits immediately.\n\n"
            "Resubscribe whenever you are ready: {link}"
        ),
        action_path=_billing_path(workspace_id),
    )


def payment_succeeded(*, workspace_id: str, amount_cents: int, plan_name: str) -> RenderedMessage:
    """A receipt. In-app only — see `EMAIL_KINDS`."""
    return RenderedMessage(
        title=f"Payment of {_money(amount_cents)} received",
        body=f"Your {plan_name} plan is paid and active.",
        subject=f"Your AgentVerse payment of {_money(amount_cents)}",
        email_body=f"We received {_money(amount_cents)} for your {plan_name} plan.\n\n{{link}}",
        action_path=_billing_path(workspace_id),
    )


def plan_changed(
    *, workspace_id: str, from_plan: str, to_plan: str, net_cents: int
) -> RenderedMessage:
    """States the proration, because a customer who sees an unexplained
    adjustment on their next invoice will ask about it either way.
    """
    if net_cents > 0:
        adjustment = f"{_money(net_cents)} is due for the rest of this period."
    elif net_cents < 0:
        adjustment = f"{_money(abs(net_cents))} has been credited to your account."
    else:
        adjustment = "There is no change to what you owe this period."
    return RenderedMessage(
        title=f"Plan changed from {from_plan} to {to_plan}",
        body=adjustment,
        subject=f"Your AgentVerse plan is now {to_plan}",
        email_body=(
            f"Your plan has changed from {from_plan} to {to_plan}.\n\n"
            f"{adjustment} We prorate to the second, so you only pay for the time you "
            "were on each plan.\n\n"
            "See the detail: {link}"
        ),
        action_path=_billing_path(workspace_id),
    )


def quota_approaching(
    *, workspace_id: str, dimension: str, percent: int, limit: int
) -> RenderedMessage:
    """The 80% nudge. In-app only: a customer at 80% has not been
    stopped, and emailing them is interrupting work that is going fine.
    """
    label = dimension.replace("_", " ")
    return RenderedMessage(
        title=f"{percent}% of your {label} allowance used",
        body=(
            f"You have used {percent}% of your included {limit:,} {label} this billing "
            "period. Upgrading raises the limit immediately."
        ),
        subject=f"You have used {percent}% of your AgentVerse {label}",
        email_body=(
            f"You have used {percent}% of your included {limit:,} {label} this billing "
            "period.\n\nUpgrade to raise the limit: {link}"
        ),
        action_path=_billing_path(workspace_id),
    )


def quota_exceeded(*, workspace_id: str, dimension: str, limit: int) -> RenderedMessage:
    """The hard stop. Emailed, because work is now blocked and the
    person who can fix it may not be the person who hit it.
    """
    label = dimension.replace("_", " ")
    return RenderedMessage(
        title=f"You have reached your {label} limit",
        body=(
            f"Your plan includes {limit:,} {label} per billing period and you have used "
            "them all. New requests are refused until the period resets or you upgrade."
        ),
        subject=f"Your AgentVerse {label} limit has been reached",
        email_body=(
            f"Your workspace has used all {limit:,} of its included {label} for this "
            "billing period.\n\nNew requests are being refused until the period resets. "
            "Upgrading raises the limit immediately and unblocks them.\n\n"
            "Upgrade: {link}"
        ),
        action_path=_billing_path(workspace_id),
    )


def credit_granted(*, workspace_id: str, amount_cents: int, reason: str) -> RenderedMessage:
    return RenderedMessage(
        title=f"{_money(amount_cents)} credit added",
        body=f"{reason}. It is applied automatically to your next invoice.",
        subject=f"{_money(amount_cents)} AgentVerse credit added",
        email_body=(
            f"{_money(amount_cents)} has been added to your account.\n\n{reason}. "
            "The credit is applied automatically to your next invoice.\n\n{link}"
        ),
        action_path=_billing_path(workspace_id),
    )


def referral_rewarded(*, workspace_id: str, amount_cents: int) -> RenderedMessage:
    return RenderedMessage(
        title=f"Referral reward: {_money(amount_cents)} credit",
        body=(
            "Someone you referred made their first payment. The credit is applied "
            "automatically to your next invoice."
        ),
        subject=f"You earned {_money(amount_cents)} AgentVerse credit",
        email_body=(
            "Someone you referred just made their first payment, so "
            f"{_money(amount_cents)} credit has been added to your account.\n\n"
            "It is applied automatically to your next invoice.\n\n"
            "See your balance: {link}"
        ),
        action_path=_billing_path(workspace_id),
    )


#: Every kind must have a renderer. Asserted by a test rather than left
#: to review: a kind with no template would raise at the moment a real
#: customer event fired, which is the worst possible time to find out.
RENDERERS: dict[NotificationKind, str] = {
    NotificationKind.TRIAL_ENDING: trial_ending.__name__,
    NotificationKind.PAYMENT_SUCCEEDED: payment_succeeded.__name__,
    NotificationKind.PAYMENT_FAILED: payment_failed.__name__,
    NotificationKind.DUNNING_REMINDER: dunning_reminder.__name__,
    NotificationKind.SUBSCRIPTION_CANCELED: subscription_canceled.__name__,
    NotificationKind.PLAN_CHANGED: plan_changed.__name__,
    NotificationKind.QUOTA_APPROACHING: quota_approaching.__name__,
    NotificationKind.QUOTA_EXCEEDED: quota_exceeded.__name__,
    NotificationKind.CREDIT_GRANTED: credit_granted.__name__,
    NotificationKind.REFERRAL_REWARDED: referral_rewarded.__name__,
}
