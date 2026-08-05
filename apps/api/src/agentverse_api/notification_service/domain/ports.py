"""Ports for the notification context."""

from __future__ import annotations

from typing import Protocol

from agentverse_api.notification_service.domain.notification import (
    Notification,
    NotificationKind,
    Severity,
)


class EmailSenderPort(Protocol):
    """The transactional email boundary.

    apps/api owns its own port rather than calling apps/web's sender over
    HTTP. That would be a new call direction (today the internal channel
    is only web → api) and would put an outbound customer email behind
    another service's availability. Two services each having their own
    adapter to an external vendor is the normal shape — the same way each
    has its own LLM provider adapter — and it duplicates no business
    logic, only a three-field interface.
    """

    async def send(self, *, to: str, subject: str, body: str) -> str | None:
        """Deliver, returning the provider's message id if it has one.

        `None` means delivered by an adapter with no id to give (the
        logging stub). Never raises for a soft failure — the caller
        records the outcome and moves on, because a notification that
        could not be sent must not roll back the billing transition that
        caused it.
        """
        ...


class NotificationRepository(Protocol):
    async def create(
        self,
        *,
        workspace_id: str,
        kind: NotificationKind,
        severity: Severity,
        title: str,
        body: str,
        action_path: str | None,
        dedupe_key: str,
        metadata: dict[str, object],
    ) -> Notification | None:
        """Record a notification, or `None` if `dedupe_key` already
        exists.

        `None` rather than raising: a duplicate is the normal outcome of
        a retried job or a redelivered webhook, and a caller should not
        have to catch an exception for the system working as designed.
        """
        ...

    async def list_for_workspace(
        self, *, workspace_id: str, limit: int, unread_only: bool
    ) -> list[Notification]: ...

    async def unread_count(self, workspace_id: str) -> int: ...

    async def mark_read(self, *, workspace_id: str, notification_id: str) -> bool:
        """`False` if it does not exist *in this workspace* — the same
        answer as "not found", so a caller cannot probe another tenant's
        notification ids (Rule 11).
        """
        ...

    async def mark_all_read(self, workspace_id: str) -> int: ...


class DeliveryRepository(Protocol):
    """The email send log.

    Separate from notifications because they answer different questions:
    a notification is what the customer was told, a delivery is whether
    the email actually left. A failed send must not erase the in-app
    notification, and a customer disputing "I was never told" needs both.
    """

    async def claim(self, *, notification_id: str, address: str) -> str | None:
        """Reserve a send, or `None` if one was already claimed for this
        notification. The unique index is what makes a retried dispatch
        send one email rather than three.
        """
        ...

    async def record_result(
        self, *, delivery_id: str, provider_message_id: str | None, error: str | None
    ) -> None: ...
