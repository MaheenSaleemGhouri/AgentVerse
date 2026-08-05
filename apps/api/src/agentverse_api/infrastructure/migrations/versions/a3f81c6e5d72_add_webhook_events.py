"""add the payment-provider webhook event log

Revision ID: a3f81c6e5d72
Revises: c5e9a1b7d380
Create Date: 2026-08-05

One table, `billing_webhook_events`, whose entire reason for existing is
the unique index on `(provider, provider_event_id)`.

Payment providers guarantee at-least-once webhook delivery, never
exactly-once: the same event arrives again after a timeout, a retry, or
simply because the provider chose to. Without this constraint a
redelivered `invoice.payment_failed` would start a second dunning cycle,
and a redelivered `checkout.session.completed` would open a second
subscription. An application-level "have I seen this?" check does not
close it, because the two deliveries can be in flight at the same time —
only the database can serialize them.

The row is written in the *same transaction* as the state change the
event causes. A row sitting at `status = 'received'` after a crash
therefore means the effect was rolled back, which the reconciliation job
treats as a finding rather than as noise.

`workspace_id` is nullable with ON DELETE SET NULL: an event can arrive
that cannot be attributed to a workspace, and it is still worth
recording. Discarding what we cannot classify is how billing incidents
become unexplainable.

Additive and reversible. Code at the previous revision has no webhook
endpoint at all, so a rollback loses only the delivery log.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a3f81c6e5d72"
down_revision = "c5e9a1b7d380"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False, server_default="stripe"),
        sa.Column("provider_event_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="received"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("provider IN ('stripe')", name="ck_billing_webhook_events_provider"),
        sa.CheckConstraint(
            "status IN ('received', 'processed', 'ignored', 'failed')",
            name="ck_billing_webhook_events_status",
        ),
    )
    op.create_index(
        "ix_billing_webhook_events_provider_event_id",
        "billing_webhook_events",
        ["provider_event_id"],
    )
    op.create_index(
        "ix_billing_webhook_events_workspace_id", "billing_webhook_events", ["workspace_id"]
    )
    # The replay guard. Scoped by provider as well as event id so a
    # second provider's id space can never collide with this one's.
    op.create_index(
        "uq_billing_webhook_events_provider_event",
        "billing_webhook_events",
        ["provider", "provider_event_id"],
        unique=True,
    )
    # The stuck-event sweep: received but never resolved, oldest first.
    op.create_index(
        "ix_billing_webhook_events_unresolved",
        "billing_webhook_events",
        ["received_at"],
        postgresql_where=sa.text("status = 'received'"),
    )


def downgrade() -> None:
    op.drop_table("billing_webhook_events")
