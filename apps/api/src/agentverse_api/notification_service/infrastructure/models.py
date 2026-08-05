"""Notification ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from agentverse_api.infrastructure.orm_base import Base

_KINDS = (
    "trial_ending",
    "payment_succeeded",
    "payment_failed",
    "dunning_reminder",
    "subscription_canceled",
    "plan_changed",
    "quota_approaching",
    "quota_exceeded",
    "credit_granted",
    "referral_rewarded",
)


class NotificationModel(Base):
    """One thing the platform told a workspace.

    Workspace-scoped, not user-scoped: billing and quota are facts about
    the workspace, and delivering "your payment failed" only to whoever
    happened to trigger the charge would leave the admin who can fix it
    uninformed.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(f"kind IN {_KINDS}", name="ck_notifications_kind"),
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')", name="ck_notifications_severity"
        ),
        # The dedupe guard. A dunning sweep that runs twice in a day, or
        # a redelivered webhook, must not tell the customer the same
        # thing twice — the key is derived from the event, so a retry
        # reproduces it and loses here.
        Index("uq_notifications_dedupe", "dedupe_key", unique=True),
        # The notification bell's only query: this workspace's unread,
        # newest first. Partial, because it never looks at read ones.
        Index(
            "ix_notifications_workspace_unread",
            "workspace_id",
            "created_at",
            postgresql_where="read_at IS NULL",
        ),
        Index("ix_notifications_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text, default="info")
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    # Relative to this app, so it survives a domain change and cannot
    # become a link to somewhere else.
    action_path: Mapped[str | None] = mapped_column(Text, default=None)
    dedupe_key: Mapped[str] = mapped_column(Text)
    notification_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, default=dict
    )
    read_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class NotificationDeliveryModel(Base):
    """Whether the email actually left.

    Separate from the notification because they answer different
    questions. A failed send must not erase the in-app entry, and a
    customer disputing "I was never told" needs both records — one says
    what they were told, the other whether it reached them.
    """

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'sent', 'failed')", name="ck_notification_deliveries_status"
        ),
        # One email per notification. Without this a retried dispatch
        # sends the customer the same message three times.
        Index("uq_notification_deliveries_once", "notification_id", "channel", unique=True),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    notification_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("notifications.id", ondelete="CASCADE"),
        index=True,
    )
    channel: Mapped[str] = mapped_column(Text, default="email")
    # The address is stored so a bounce can be traced to what was
    # actually used, which may differ from the workspace's current
    # billing email by the time anyone looks.
    address: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pending")
    provider_message_id: Mapped[str | None] = mapped_column(Text, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(default=None)
