"""add outbound webhooks and per-plan API rate limits

Revision ID: e27b8f3d05a1
Revises: d15a7c94b2e0
Create Date: 2026-08-06

Two webhook tables, and one column on `plans`.

**`plans.api_rate_limit_per_minute`** puts the rate limit with the rest
of the pricing configuration, because it is a packaging decision rather
than an implementation constant (Rule 3). NULL is unlimited — the same
convention every other quota on that row uses, so "not configured" never
silently means zero. Seeded per tier below; Enterprise is left NULL,
because a negotiated contract is exactly where a published number stops
applying.

**`webhook_deliveries` is a table, not a Redis stream.** A delivery
retried over roughly two hours has to survive a worker restart, and
Redis is never the system of record (Rule 13). The worker claims due
rows with `FOR UPDATE SKIP LOCKED`, so replicas drain the same table
without coordinating and without blocking each other.

The unique index on `(endpoint_id, event_id)` is what makes dispatch
idempotent: `event_id` is derived from the row that caused the event, so
a redelivered job produces the same key and is absorbed by the index
rather than sending the customer a duplicate (Rule 14).

The signing secret is stored under the envelope vault — sealed, not
hashed. Unlike an API key the customer must be able to read it back to
configure their verifier, so a one-way hash would make the feature
unusable. Same three columns as the MCP credentials and SSO client
secrets already use.

Additive and reversible. Code at the previous revision has neither table
nor the column, so a rollback loses webhook configuration and delivery
history, and nothing else.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e27b8f3d05a1"
down_revision = "d15a7c94b2e0"
branch_labels = None
depends_on = None

_STATUSES = "('pending', 'delivering', 'delivered', 'failed')"

#: Published per-minute API allowances. Enterprise is NULL because a
#: negotiated contract is where a published number stops applying — not
#: because it is unlimited by accident.
_TIER_LIMITS: tuple[tuple[str, int | None], ...] = (
    ("free", 60),
    ("pro", 600),
    ("team", 3_000),
    ("enterprise", None),
)


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("api_rate_limit_per_minute", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_plans_api_rate_limit_non_negative",
        "plans",
        "api_rate_limit_per_minute IS NULL OR api_rate_limit_per_minute >= 0",
    )
    plans = sa.table(
        "plans",
        sa.column("slug", sa.Text),
        sa.column("api_rate_limit_per_minute", sa.Integer),
    )
    for slug, limit in _TIER_LIMITS:
        if limit is None:
            continue
        op.execute(
            plans.update().where(plans.c.slug == slug).values(api_rate_limit_per_minute=limit)
        )

    op.create_table(
        "webhook_endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        # A Postgres array rather than a join table: the set is small,
        # always read whole, and never queried across workspaces.
        sa.Column(
            "events",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        # Sealed under the envelope vault, not hashed — the customer must
        # read it back to configure their verifier.
        sa.Column("secret_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("wrapped_dek", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "consecutive_failures >= 0", name="ck_webhook_endpoints_failures_non_negative"
        ),
        # Enforced in the database as well as the schema: a row inserted
        # by a fixture or a migration bypasses Pydantic, and a relative
        # URL would then fail at delivery time rather than at write time.
        sa.CheckConstraint(
            "url LIKE 'http://%' OR url LIKE 'https://%'", name="ck_webhook_url_scheme"
        ),
    )
    op.create_index("ix_webhook_endpoints_workspace_id", "webhook_endpoints", ["workspace_id"])
    op.create_index(
        "ix_webhook_endpoints_workspace", "webhook_endpoints", ["workspace_id", "is_active"]
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "endpoint_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        # Derived from the source row, never random — that is what makes
        # a redelivered dispatch idempotent.
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_response_status", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(f"status IN {_STATUSES}", name="ck_webhook_deliveries_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_webhook_deliveries_attempts_non_negative"),
    )
    op.create_index("ix_webhook_deliveries_workspace_id", "webhook_deliveries", ["workspace_id"])
    op.create_index("ix_webhook_deliveries_endpoint_id", "webhook_deliveries", ["endpoint_id"])
    op.create_index("ix_webhook_deliveries_event_type", "webhook_deliveries", ["event_type"])
    # Idempotency, enforced by the database rather than by a check two
    # concurrent dispatches would both pass.
    op.create_index(
        "uq_webhook_deliveries_event",
        "webhook_deliveries",
        ["endpoint_id", "event_id"],
        unique=True,
    )
    # The drainer's query. Partial, so it stays proportional to the
    # backlog rather than to the delivery history, which never shrinks.
    op.create_index(
        "ix_webhook_deliveries_due",
        "webhook_deliveries",
        ["next_attempt_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_webhook_deliveries_workspace",
        "webhook_deliveries",
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_endpoints")
    op.drop_constraint("ck_plans_api_rate_limit_non_negative", "plans", type_="check")
    op.drop_column("plans", "api_rate_limit_per_minute")
