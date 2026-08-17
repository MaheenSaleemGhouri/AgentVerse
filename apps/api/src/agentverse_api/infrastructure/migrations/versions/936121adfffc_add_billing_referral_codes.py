"""add billing referral codes

Revision ID: 936121adfffc
Revises: 45c7e4928b44
Create Date: 2026-08-14

`referral_code(workspace_id)` (billing_service/domain/referral.py) is a
one-way sha256 hash with nothing stored — by design, so a workspace's
code needs no table to be *displayed*, and is the same every time it is
shown. But redeeming a code someone pasted into a signup flow needs the
opposite direction: given only the 8-character code, resolve which
workspace it belongs to. A hash cannot be reversed, so this table is a
minimal reverse index, populated lazily and idempotently the first time
each workspace's code is ever requested (`CreditService.ensure_code`) —
never computed differently than `referral_code()` computes it.

This closes a real gap, not a speculative one: before this migration,
`CreditService.attribute()` (meant to be called when a referred
workspace signs up, per its own docstring) had no way to turn a client-
supplied code into a `referrer_workspace_id` at all, and had zero
production call sites as a result — the referral loop existed in the
schema and the domain logic but could never actually be triggered.

Additive and reversible: `downgrade()` drops the table cleanly. No
existing table gains or loses a column, and no other table references
this one.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "936121adfffc"
down_revision = "45c7e4928b44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_referral_codes",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("workspace_id"),
    )
    # Unique, not just indexed: two workspaces resolving to the same code
    # would make redemption ambiguous — the same guarantee `referral_code`'s
    # own docstring already relies on (8 hex chars against a workspace
    # count nowhere near 4 billion), enforced here rather than merely hoped.
    op.create_index(
        "ix_billing_referral_codes_code", "billing_referral_codes", ["code"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_billing_referral_codes_code", table_name="billing_referral_codes")
    op.drop_table("billing_referral_codes")
