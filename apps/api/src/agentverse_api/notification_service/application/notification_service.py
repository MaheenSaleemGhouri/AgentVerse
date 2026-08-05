"""Raising notifications, and getting the ones that need an inbox there.

One rule shapes everything: **a notification never fails the thing that
caused it.** A payment webhook that transitions a subscription and then
cannot send an email has still processed the payment correctly, and
returning a 5xx would make the provider retry a transition that already
succeeded. So `raise_` swallows delivery failures, records them on the
delivery row, and returns.

The trade is deliberate and stated: an undelivered email is recoverable
(the row says `failed`, and the in-app notification is still there), and
a rolled-back billing transition is not.

**Deduplication is by a key derived from the event, not a timestamp.**
A dunning sweep that runs twice in a day, a redelivered webhook, and a
retried job all produce the same key and therefore one notification. A
key containing `now()` would produce three, which is exactly the
behaviour that trains customers to ignore billing email.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from agentverse_api.notification_service.domain.notification import (
    Notification,
    NotificationKind,
    Severity,
    default_severity,
    wants_email,
)
from agentverse_api.notification_service.domain.ports import (
    DeliveryRepository,
    EmailSenderPort,
    NotificationRepository,
)
from agentverse_api.notification_service.domain.templates import RenderedMessage

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class NotificationService:
    notifications: NotificationRepository
    deliveries: DeliveryRepository
    email: EmailSenderPort
    #: Where a relative `action_path` resolves to in an email. Emails
    #: need an absolute URL; the in-app entry keeps the relative path,
    #: which is why the two are not stored as one value.
    app_base_url: str = ""
    now: Callable[[], datetime] = field(default=_utc_now)

    async def raise_(
        self,
        *,
        workspace_id: str,
        kind: NotificationKind,
        message: RenderedMessage,
        dedupe_key: str,
        recipient: str | None = None,
        severity: Severity | None = None,
        metadata: dict[str, object] | None = None,
    ) -> Notification | None:
        """Record a notification and, where the kind warrants it, email it.

        `None` means the dedupe key was already used — the normal outcome
        of a retry, not a failure.

        `recipient=None` records the in-app notification and skips the
        email rather than guessing an address. Emailing a fallback (the
        workspace creator, say) would send billing mail to whoever
        happened to sign up rather than to whoever handles billing.
        """
        notification = await self.notifications.create(
            workspace_id=workspace_id,
            kind=kind,
            severity=severity or default_severity(kind),
            title=message.title,
            body=message.body,
            action_path=message.action_path,
            dedupe_key=dedupe_key,
            metadata=metadata or {},
        )
        if notification is None:
            logger.info(
                "notification_deduplicated",
                extra={"workspace_id": workspace_id, "kind": kind.value},
            )
            return None

        if wants_email(kind) and recipient:
            await self._try_email(
                notification_id=notification.id, recipient=recipient, message=message
            )
        return notification

    async def _try_email(
        self, *, notification_id: str, recipient: str, message: RenderedMessage
    ) -> None:
        """Send, recording the outcome either way. Never raises.

        The claim comes first and its unique index is what makes a
        retried dispatch send one email rather than three — an
        application-level check cannot serialize two concurrent
        dispatches.
        """
        delivery_id = await self.deliveries.claim(
            notification_id=notification_id, address=recipient
        )
        if delivery_id is None:
            return

        body = message.email_body.replace(
            "{link}", f"{self.app_base_url}{message.action_path or ''}"
        )
        try:
            provider_message_id = await self.email.send(
                to=recipient, subject=message.subject, body=body
            )
        except Exception as exc:
            # Recorded, not raised. The billing transition that caused
            # this has already succeeded; failing now would make the
            # provider retry it.
            await self.deliveries.record_result(
                delivery_id=delivery_id,
                provider_message_id=None,
                error=f"{type(exc).__name__}: {exc}",
            )
            logger.exception(
                "notification_email_failed", extra={"notification_id": notification_id}
            )
            return
        await self.deliveries.record_result(
            delivery_id=delivery_id,
            provider_message_id=provider_message_id,
            error=None,
        )

    # ---- reads -------------------------------------------------------

    async def list_for(
        self, *, workspace_id: str, limit: int = 50, unread_only: bool = False
    ) -> list[Notification]:
        return await self.notifications.list_for_workspace(
            workspace_id=workspace_id, limit=limit, unread_only=unread_only
        )

    async def unread_count(self, workspace_id: str) -> int:
        return await self.notifications.unread_count(workspace_id)

    async def mark_read(self, *, workspace_id: str, notification_id: str) -> bool:
        return await self.notifications.mark_read(
            workspace_id=workspace_id, notification_id=notification_id
        )

    async def mark_all_read(self, workspace_id: str) -> int:
        return await self.notifications.mark_all_read(workspace_id)
