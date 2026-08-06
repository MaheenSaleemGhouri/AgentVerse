"""Webhook endpoints and the events they subscribe to.

Pure — no I/O, no framework.

**Event types are a closed set.** A customer subscribing to a typo gets
an endpoint that never fires and no indication why, and a free-text
`event_type` column means the platform can never enumerate what it
actually emits. The enum is the contract; adding a member is an additive
API change, removing one is breaking (§7).

**An endpoint disables itself.** After enough consecutive failures the
endpoint is turned off rather than retried forever. A customer who
decommissioned a URL months ago should not still be generating delivery
attempts, and — more importantly — a queue full of doomed deliveries is
how a real outage's backlog gets buried.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class WebhookEvent(StrEnum):
    """Everything the platform will deliver.

    Each maps to something the system already records durably, so no
    event here can be emitted from a place that might not have committed
    — the same rule the metered billing dimensions follow.
    """

    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    AGENT_PUBLISHED = "agent.published"
    QUOTA_EXCEEDED = "billing.quota_exceeded"
    SUBSCRIPTION_CHANGED = "billing.subscription_changed"
    LISTING_APPROVED = "marketplace.listing_approved"
    LISTING_INSTALLED = "marketplace.listing_installed"


class InvalidEventTypeError(Exception):
    """Maps to HTTP 422, naming what was accepted."""

    def __init__(self, unknown: list[str]) -> None:
        self.unknown = unknown
        super().__init__(
            f"Unknown event types: {', '.join(sorted(unknown))}. "
            f"Valid: {', '.join(sorted(e.value for e in WebhookEvent))}"
        )


def parse_events(raw: list[str]) -> frozenset[WebhookEvent]:
    """Validate a subscription list, reporting every bad name at once.

    An empty list is refused rather than treated as "all": a customer who
    forgot the field would silently receive every event the platform
    emits, including ones added later, at whatever volume they arrive.
    Subscribing to everything should be a thing you typed.
    """
    if not raw:
        raise InvalidEventTypeError([])
    valid = {event.value for event in WebhookEvent}
    unknown = [name for name in raw if name not in valid]
    if unknown:
        raise InvalidEventTypeError(unknown)
    return frozenset(WebhookEvent(name) for name in raw)


#: Consecutive failed deliveries before an endpoint is switched off. The
#: counter resets on any success, so an endpoint with intermittent
#: trouble is never disabled — only one that has stopped answering.
FAILURE_THRESHOLD = 20


@dataclass(frozen=True, slots=True)
class WebhookEndpoint:
    """One customer URL, and what it wants."""

    id: str
    workspace_id: str
    url: str
    description: str
    events: frozenset[WebhookEvent]
    is_active: bool
    consecutive_failures: int
    disabled_at: datetime | None
    disabled_reason: str | None
    created_at: datetime
    updated_at: datetime

    def wants(self, event: WebhookEvent) -> bool:
        """Only active endpoints receive anything.

        Checked here rather than at every dispatch site, so "disabled"
        cannot mean different things in two places.
        """
        return self.is_active and event in self.events


def should_disable(consecutive_failures: int) -> bool:
    return consecutive_failures >= FAILURE_THRESHOLD


def next_failure_count(*, current: int, delivered: bool) -> int:
    """Reset on success, increment on failure.

    Reset rather than decay: an endpoint that answered is working now,
    and carrying old failures forward would eventually disable a healthy
    URL that had a bad week months ago.
    """
    return 0 if delivered else current + 1
