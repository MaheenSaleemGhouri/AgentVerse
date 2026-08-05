"""add notifications and email delivery log

Revision ID: f0a4c9e21b58
Revises: e61d5a83f907
Create Date: 2026-08-05

Two tables that answer different questions.

`notifications` is what the platform told a workspace. Workspace-scoped
rather than user-scoped on purpose: billing and quota are facts about the
workspace, and delivering "your payment failed" only to whoever happened
to trigger the charge would leave the admin who can actually fix it
uninformed. Read state is per workspace for the same reason — someone
dealt with it, and it stops nagging everyone.

`notification_deliveries` is whether the email left. Kept separate
because a failed send must not erase the in-app entry, and a customer
disputing "I was never told" needs both records.

The two unique indexes are the load-bearing part:

- `notifications.dedupe_key` — derived from the event that caused it, so
  a dunning sweep that runs twice in a day, or a redelivered webhook,
  loses here rather than telling the customer the same thing twice.
- `(notification_id, channel)` on deliveries — without it a retried
  dispatch sends the same message three times.

Additive and reversible. Code at the previous revision sends no
notifications, so a rollback loses nothing it was recording.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f0a4c9e21b58"
down_revision = "e61d5a83f907"
branch_labels = None
depends_on = None

_KINDS = (
    "('trial_ending', 'payment_succeeded', 'payment_failed', 'dunning_reminder', "
    "'subscription_canceled', 'plan_changed', 'quota_approaching', 'quota_exceeded', "
    "'credit_granted', 'referral_rewarded')"
)


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False, server_default="info"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        # Relative to this app, so it survives a domain change and cannot
        # become a link to somewhere else.
        sa.Column("action_path", sa.Text(), nullable=True),
        sa.Column("dedupe_key", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(f"kind IN {_KINDS}", name="ck_notifications_kind"),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')", name="ck_notifications_severity"
        ),
    )
    op.create_index("ix_notifications_workspace_id", "notifications", ["workspace_id"])
    # The dedupe guard.
    op.create_index("uq_notifications_dedupe", "notifications", ["dedupe_key"], unique=True)
    # The notification bell's only query: this workspace's unread,
    # newest first. Partial, because it never looks at read ones.
    op.create_index(
        "ix_notifications_workspace_unread",
        "notifications",
        ["workspace_id", "created_at"],
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_index(
        "ix_notifications_workspace_created", "notifications", ["workspace_id", "created_at"]
    )

    op.create_table(
        "notification_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "notification_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("notifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.Text(), nullable=False, server_default="email"),
        # Stored so a bounce can be traced to the address actually used,
        # which may differ from the workspace's current billing email by
        # the time anyone looks.
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("provider_message_id", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed')", name="ck_notification_deliveries_status"
        ),
    )
    op.create_index(
        "ix_notification_deliveries_notification_id",
        "notification_deliveries",
        ["notification_id"],
    )
    # One email per notification per channel.
    op.create_index(
        "uq_notification_deliveries_once",
        "notification_deliveries",
        ["notification_id", "channel"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("notification_deliveries")
    op.drop_table("notifications")
