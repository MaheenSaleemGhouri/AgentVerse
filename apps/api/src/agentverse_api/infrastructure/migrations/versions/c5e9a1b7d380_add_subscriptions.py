"""add billing customers, subscriptions and the transition event log

Revision ID: c5e9a1b7d380
Revises: f7d2c8b3a604
Create Date: 2026-08-05

Three tables, one per fact:

- `billing_customers` — the workspace's identity at the payment
  processor. One per workspace, for the workspace's whole life, so a
  returning customer keeps their saved payment methods and invoice
  history.
- `billing_subscriptions` — what the workspace is paying for and where it
  is in its lifecycle. At most one live row per workspace, enforced by a
  partial unique index rather than application logic.
- `subscription_events` — append-only record of every state transition,
  with an `idempotency_key` unique index that makes a redelivered webhook
  or a re-run job a no-op instead of a second transition.

Two CHECK constraints encode invariants that would otherwise be
comments. `status = 'past_due'` requires `past_due_since`, so a
subscription can never sit past due with no dunning clock to close the
window; `status = 'canceled'` requires `canceled_at`, so "when did this
end" is always answerable.

`plan_id` references `plans` with ON DELETE RESTRICT. Cascading would
delete paying customers' subscriptions along with a plan row; nulling
would leave subscriptions nobody can price. Retiring a plan is
`is_active = false`, which is what that column is for.

Enum-like columns are TEXT + CHECK, not Postgres ENUM — `ALTER TYPE ...
DROP VALUE` does not exist, so an ENUM would make this migration
irreversible (Rule 19).

Additive and reversible: nothing existing is altered, and `downgrade()`
drops the three tables in FK order. Code at the previous revision
resolves every workspace to the Free plan and never reads these tables,
so a rollback is safe — it loses subscription state, which is why the
rollback note for the release says to reconcile from the payment
processor if one is ever needed after real subscriptions exist.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c5e9a1b7d380"
down_revision = "f7d2c8b3a604"
branch_labels = None
depends_on = None

_STATUSES = "('trialing', 'active', 'past_due', 'paused', 'canceled')"


def upgrade() -> None:
    op.create_table(
        "billing_customers",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.Text(), nullable=False, server_default="stripe"),
        sa.Column("provider_customer_id", sa.Text(), nullable=False),
        sa.Column("billing_email", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("provider IN ('stripe')", name="ck_billing_customers_provider"),
        # Both unique: one processor account per workspace, and one
        # workspace per processor account. Either duplication would put
        # one tenant's invoices on another tenant's account.
        sa.UniqueConstraint("workspace_id", name="uq_billing_customers_workspace"),
        sa.UniqueConstraint("provider_customer_id", name="uq_billing_customers_provider_id"),
    )
    op.create_index("ix_billing_customers_workspace_id", "billing_customers", ["workspace_id"])
    op.create_index(
        "ix_billing_customers_provider_customer_id",
        "billing_customers",
        ["provider_customer_id"],
    )

    op.create_table(
        "billing_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        # Not `interval`: INTERVAL is a Postgres type name, and a column
        # called that needs quoting in every hand-written query forever.
        sa.Column("billing_interval", sa.Text(), nullable=False, server_default="monthly"),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("past_due_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_subscription_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(f"status IN {_STATUSES}", name="ck_billing_subscriptions_status"),
        sa.CheckConstraint(
            "billing_interval IN ('monthly', 'annual')",
            name="ck_billing_subscriptions_interval",
        ),
        sa.CheckConstraint(
            "current_period_end > current_period_start",
            name="ck_billing_subscriptions_period_ordered",
        ),
        sa.CheckConstraint(
            "status <> 'past_due' OR past_due_since IS NOT NULL",
            name="ck_billing_subscriptions_past_due_has_clock",
        ),
        sa.CheckConstraint(
            "status <> 'canceled' OR canceled_at IS NOT NULL",
            name="ck_billing_subscriptions_canceled_has_timestamp",
        ),
        sa.UniqueConstraint(
            "provider_subscription_id", name="uq_billing_subscriptions_provider_id"
        ),
    )
    op.create_index(
        "ix_billing_subscriptions_workspace_id", "billing_subscriptions", ["workspace_id"]
    )
    op.create_index("ix_billing_subscriptions_plan_id", "billing_subscriptions", ["plan_id"])
    op.create_index("ix_billing_subscriptions_status", "billing_subscriptions", ["status"])
    op.create_index(
        "ix_billing_subscriptions_provider_subscription_id",
        "billing_subscriptions",
        ["provider_subscription_id"],
    )
    op.create_index(
        "ix_billing_subscriptions_workspace_status",
        "billing_subscriptions",
        ["workspace_id", "status"],
    )
    # At most one live subscription per workspace. Partial, because a
    # workspace legitimately accumulates canceled rows — that is its
    # billing history, and a plain unique index would force deleting it.
    op.create_index(
        "uq_billing_subscriptions_one_live_per_workspace",
        "billing_subscriptions",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'canceled'"),
    )
    # The dunning sweep's only query: every past-due subscription, oldest
    # failure first. Partial because that job never looks at any other
    # status.
    op.create_index(
        "ix_billing_subscriptions_dunning",
        "billing_subscriptions",
        ["past_due_since"],
        postgresql_where=sa.text("status = 'past_due'"),
    )

    op.create_table(
        "subscription_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("billing_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Denormalized so every read filters by tenant without a join
        # (Rule 11).
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=False),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            f"from_status IN {_STATUSES}", name="ck_subscription_events_from_status"
        ),
        sa.CheckConstraint(f"to_status IN {_STATUSES}", name="ck_subscription_events_to_status"),
        # The replay guard. A redelivered webhook carrying the same key
        # hits this constraint instead of transitioning a second time.
        sa.UniqueConstraint("idempotency_key", name="uq_subscription_events_idempotency_key"),
    )
    op.create_index(
        "ix_subscription_events_subscription_id", "subscription_events", ["subscription_id"]
    )
    op.create_index("ix_subscription_events_workspace_id", "subscription_events", ["workspace_id"])
    op.create_index(
        "ix_subscription_events_idempotency_key", "subscription_events", ["idempotency_key"]
    )
    op.create_index(
        "ix_subscription_events_workspace_time",
        "subscription_events",
        ["workspace_id", "occurred_at"],
    )
    op.create_index(
        "ix_subscription_events_subscription_time",
        "subscription_events",
        ["subscription_id", "occurred_at"],
    )


def downgrade() -> None:
    # FK order: events reference subscriptions, subscriptions reference
    # plans (left in place) and workspaces.
    op.drop_table("subscription_events")
    op.drop_table("billing_subscriptions")
    op.drop_table("billing_customers")
