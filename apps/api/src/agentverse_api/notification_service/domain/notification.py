"""What the platform tells a workspace, and through which channel.

Pure — no I/O, no framework. The kinds below are a closed set on
purpose: a notification is a thing a customer receives, and an
open-ended `type: str` is how a system ends up sending three
subtly-different "payment failed" messages written by three different
call sites.

**Transactional and marketing are separated at the type level.** Every
kind here is transactional — it is about this workspace's own account,
service or money, and a customer cannot meaningfully opt out of being
told their subscription is about to be canceled. Marketing email is a
different system with a different consent model
(`email-marketing-expert`), and the separation being structural rather
than a boolean on a row is what keeps a campaign from ever being sent
down this path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class NotificationKind(StrEnum):
    """Every notification this platform sends.

    Named for what happened, not for what the UI does with it — a kind
    called `show_red_banner` would be a rendering decision leaking into
    the event that caused it.
    """

    # Billing lifecycle.
    TRIAL_ENDING = "trial_ending"
    PAYMENT_SUCCEEDED = "payment_succeeded"
    PAYMENT_FAILED = "payment_failed"
    DUNNING_REMINDER = "dunning_reminder"
    SUBSCRIPTION_CANCELED = "subscription_canceled"
    PLAN_CHANGED = "plan_changed"
    # Usage and quota.
    QUOTA_APPROACHING = "quota_approaching"
    QUOTA_EXCEEDED = "quota_exceeded"
    # Credit and growth.
    CREDIT_GRANTED = "credit_granted"
    REFERRAL_REWARDED = "referral_rewarded"


class Severity(StrEnum):
    """How much attention a notification needs.

    Drives ordering and styling, not delivery: an `INFO` notification is
    still delivered, it just does not interrupt. Kept separate from
    `NotificationKind` so the same kind could be raised at a different
    severity by context — a quota warning at 80% and at 100% are the
    same kind and genuinely different urgencies.
    """

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Channel(StrEnum):
    IN_APP = "in_app"
    EMAIL = "email"


#: Which kinds are worth an email as well as an in-app entry.
#:
#: The distinction is whether the customer needs to act *outside* the
#: product. A failed payment and an exhausted quota block work and need
#: a card updated or a plan changed, so they reach the inbox. A
#: successful payment is a receipt — real, worth recording, but a
#: customer who is served well does not need an email every month
#: telling them nothing changed.
EMAIL_KINDS: frozenset[NotificationKind] = frozenset(
    {
        NotificationKind.TRIAL_ENDING,
        NotificationKind.PAYMENT_FAILED,
        NotificationKind.DUNNING_REMINDER,
        NotificationKind.SUBSCRIPTION_CANCELED,
        NotificationKind.QUOTA_EXCEEDED,
        NotificationKind.REFERRAL_REWARDED,
    }
)

#: Default severity per kind. A caller may raise it (a quota warning at
#: 100% rather than 80%) but never invents one from nothing, so the
#: baseline urgency of each kind is decided once.
_DEFAULT_SEVERITY: dict[NotificationKind, Severity] = {
    NotificationKind.TRIAL_ENDING: Severity.WARNING,
    NotificationKind.PAYMENT_SUCCEEDED: Severity.INFO,
    NotificationKind.PAYMENT_FAILED: Severity.CRITICAL,
    NotificationKind.DUNNING_REMINDER: Severity.CRITICAL,
    NotificationKind.SUBSCRIPTION_CANCELED: Severity.WARNING,
    NotificationKind.PLAN_CHANGED: Severity.INFO,
    NotificationKind.QUOTA_APPROACHING: Severity.WARNING,
    NotificationKind.QUOTA_EXCEEDED: Severity.CRITICAL,
    NotificationKind.CREDIT_GRANTED: Severity.INFO,
    NotificationKind.REFERRAL_REWARDED: Severity.INFO,
}


def default_severity(kind: NotificationKind) -> Severity:
    return _DEFAULT_SEVERITY[kind]


def wants_email(kind: NotificationKind) -> bool:
    return kind in EMAIL_KINDS


@dataclass(frozen=True, slots=True)
class Notification:
    """One thing the platform told a workspace.

    Workspace-scoped rather than user-scoped: billing and quota are facts
    about the workspace, and delivering "your payment failed" to only
    whoever happened to trigger the charge would leave the admin who can
    actually fix it uninformed. Read state is therefore per workspace
    too — someone dealt with it, and it stops nagging everyone.
    """

    id: str
    workspace_id: str
    kind: NotificationKind
    severity: Severity
    title: str
    body: str
    #: Where the customer should go to act on it. Relative to this app,
    #: so it survives a domain change and cannot become a link to
    #: somewhere else.
    action_path: str | None
    read_at: datetime | None
    created_at: datetime
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def is_read(self) -> bool:
        return self.read_at is not None
