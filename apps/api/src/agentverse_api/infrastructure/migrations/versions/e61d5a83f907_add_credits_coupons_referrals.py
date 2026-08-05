"""add credits, coupons and referrals

Revision ID: e61d5a83f907
Revises: d94b7f2a1c68
Create Date: 2026-08-05

Five tables, three mechanisms.

**Credits** are a balance row plus an append-only ledger. The ledger is
the truth and the balance is a projection of it — not redundancy: a bare
balance answers "how much" and nothing else, and the first question a
customer asks about credit is always "why". Decrements take
`SELECT ... FOR UPDATE` on the balance row, which is what stops two
concurrent spends from each seeing the same balance and both approving.

**Coupons** grant account credit. They are deliberately *not* the
payment provider's promotion codes, which discount a subscription's
price at checkout and are already passed through by the checkout route.
Two mechanisms with no overlap: a provider code changes the price of the
plan being bought, a coupon here puts money on the account that survives
plan changes and cancellation.

**Referrals** record who referred whom. Attribution is written
server-side when the referred workspace is created, never reconstructed
from a client cookie — a cookie is lost on a device switch and forged in
a console, and either failure lands directly in someone's balance.

The constraints worth naming individually:

- `balance_cents >= 0` on both the balance and every ledger row: a
  negative balance means the platform is owed money through a mechanism
  with no way to collect it.
- unique `idempotency_key` on the ledger: a retried coupon redemption or
  a replayed referral payout loses here rather than doubling a balance.
- unique `(coupon_id, workspace_id)`: without it a workspace redeems the
  same code repeatedly and a fixed-cents coupon becomes an unlimited
  credit tap.
- unique `referred_workspace_id` and `referrer <> referred`: a workspace
  can be referred once, and never by itself.

Additive and reversible. Code at the previous revision grants no credit,
so a rollback loses nothing it was tracking.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e61d5a83f907"
down_revision = "d94b7f2a1c68"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_credits",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("balance_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("currency", sa.Text(), nullable=False, server_default="usd"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("balance_cents >= 0", name="ck_billing_credits_non_negative"),
    )

    op.create_table(
        "billing_credit_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        # Always a positive magnitude; `reason` decides the direction. A
        # signed amount would make "did this add or subtract" depend on
        # reading the sign correctly at every call site.
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("balance_after_cents", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("amount_cents > 0", name="ck_billing_credit_transactions_positive"),
        sa.CheckConstraint(
            "balance_after_cents >= 0", name="ck_billing_credit_transactions_balance"
        ),
    )
    op.create_index(
        "ix_billing_credit_transactions_workspace_id",
        "billing_credit_transactions",
        ["workspace_id"],
    )
    op.create_index(
        "uq_billing_credit_transactions_idempotency",
        "billing_credit_transactions",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_billing_credit_transactions_workspace_time",
        "billing_credit_transactions",
        ["workspace_id", "created_at"],
    )

    op.create_table(
        "billing_coupons",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        # Stored normalized (trimmed, uppercase) so the unique index *is*
        # the case-insensitive uniqueness rule, rather than something the
        # application has to remember to apply on every lookup.
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_redemptions", sa.Integer(), nullable=True),
        sa.Column("redemption_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "eligible_plan_slugs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("credit_expires_after_days", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "kind IN ('fixed_cents', 'percent_off')", name="ck_billing_coupons_kind"
        ),
        sa.CheckConstraint("value > 0", name="ck_billing_coupons_value_positive"),
        # A percentage above 100 would grant more credit than the plan
        # costs — free money with a typo as its only cause.
        sa.CheckConstraint(
            "kind <> 'percent_off' OR value <= 100", name="ck_billing_coupons_percent_range"
        ),
        sa.CheckConstraint(
            "max_redemptions IS NULL OR max_redemptions > 0",
            name="ck_billing_coupons_max_redemptions",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until > valid_from",
            name="ck_billing_coupons_validity_ordered",
        ),
        sa.UniqueConstraint("code", name="uq_billing_coupons_code"),
    )
    op.create_index("ix_billing_coupons_code", "billing_coupons", ["code"])

    op.create_table(
        "billing_coupon_redemptions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "coupon_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("billing_coupons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("credited_cents", sa.BigInteger(), nullable=False),
        sa.Column("redeemed_by_user_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_billing_coupon_redemptions_coupon_id", "billing_coupon_redemptions", ["coupon_id"]
    )
    op.create_index(
        "ix_billing_coupon_redemptions_workspace_id",
        "billing_coupon_redemptions",
        ["workspace_id"],
    )
    # Without this a workspace redeems the same code repeatedly, and a
    # fixed-cents coupon becomes an unlimited credit tap.
    op.create_index(
        "uq_billing_coupon_redemptions_once",
        "billing_coupon_redemptions",
        ["coupon_id", "workspace_id"],
        unique=True,
    )

    op.create_table(
        "billing_referrals",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "referrer_workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "referred_workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        # Stored per row rather than read from a constant at payout, so a
        # campaign that changes the amounts does not retroactively change
        # what an existing referral was promised.
        sa.Column("referrer_reward_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("referred_reward_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("qualified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rewarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('pending', 'qualified', 'rewarded', 'voided')",
            name="ck_billing_referrals_status",
        ),
        # The obvious abuse, made structurally impossible.
        sa.CheckConstraint(
            "referrer_workspace_id <> referred_workspace_id",
            name="ck_billing_referrals_not_self",
        ),
    )
    op.create_index(
        "ix_billing_referrals_referrer_workspace_id",
        "billing_referrals",
        ["referrer_workspace_id"],
    )
    op.create_index(
        "ix_billing_referrals_referred_workspace_id",
        "billing_referrals",
        ["referred_workspace_id"],
    )
    op.create_index("ix_billing_referrals_code", "billing_referrals", ["code"])
    op.create_index("ix_billing_referrals_status", "billing_referrals", ["status"])
    # A workspace can be referred exactly once; without this a code could
    # be re-applied to the same workspace to farm rewards.
    op.create_index(
        "uq_billing_referrals_referred_once",
        "billing_referrals",
        ["referred_workspace_id"],
        unique=True,
    )
    # The referrer's dashboard query: "my referrals, by status".
    op.create_index(
        "ix_billing_referrals_referrer_status",
        "billing_referrals",
        ["referrer_workspace_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("billing_referrals")
    op.drop_table("billing_coupon_redemptions")
    op.drop_table("billing_coupons")
    op.drop_table("billing_credit_transactions")
    op.drop_table("billing_credits")
