"""add verification consumed_at

Revision ID: a7c3e9f2b1d4
Revises: f1a2b3c4d5e6
Create Date: 2026-08-01

Increment 5 reuses Better Auth's `verifications` table to store
email-invitation tokens (ADR-0005: apps/api-domain use of a
Better-Auth-owned table, via Alembic) — `identifier` carries the
target/role/inviter/email, `value` carries the random token. This
column enforces single-use: an invitation is consumed exactly once.
Better Auth's own rows (reset-password, email verification) never
populate it — it manages their lifecycle itself.

Also indexes `value`, since invitation lookup is `WHERE value = :token`
and the column previously had no index at all.

Additive and reversible (Rule 19): one nullable column and one index,
nothing existing altered.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a7c3e9f2b1d4"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "verifications",
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_verifications_value"), "verifications", ["value"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_verifications_value"), table_name="verifications")
    op.drop_column("verifications", "consumed_at")
