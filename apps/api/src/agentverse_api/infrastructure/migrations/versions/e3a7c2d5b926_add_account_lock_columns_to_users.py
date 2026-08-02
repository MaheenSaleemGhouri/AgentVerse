"""add account lock columns to users

Revision ID: e3a7c2d5b926
Revises: d2f6b9e4a815
Create Date: 2026-08-01

Increment 7.5: account locking after repeated failed sign-ins, enforced
inside the already-customized `password.verify` override in
`apps/web/lib/password-hashing.ts` — the same Better Auth extension
point ADR-0005 used for Argon2id, so no new interception layer is
introduced.

Both columns are non-null with safe defaults, so every pre-existing user
starts unlocked with a zero failure count.

Additive and reversible (Rule 19): two new columns, nothing existing
altered.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e3a7c2d5b926"
down_revision = "d2f6b9e4a815"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")
