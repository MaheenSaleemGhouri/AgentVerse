"""add two_factor table and grandfather existing users as verified

Revision ID: c1e5a8d3f704
Revises: b9d4f6a1c8e2
Create Date: 2026-08-01

Increment 7.1 + 7.2.

**7.2 — 2FA.** Better Auth's own vetted `twoFactor()` plugin, not
hand-rolled TOTP (the same "vetted library, never custom crypto"
reasoning ADR-0005 used for Argon2id). Its documented schema is authored
here by Alembic in snake_case, exactly the precedent `jwks` set — Better
Auth's own migration CLI is never run against this database. `apps/api`'s
JWT verification needs zero changes: 2FA gates *sign-in*, before a
session/JWT exists.

**7.1 — email verification enforcement.** `requireEmailVerification`
flips to true in `apps/web/lib/auth.ts` alongside this migration. The
one-time backfill below marks every *pre-existing* user verified so
enforcement applies only to new signups — without it, flipping the flag
would lock every current user out of their own account on next sign-in,
which is a data-loss-grade regression, not a security improvement.
OAuth users are included in the same backfill (the provider already
vouched for the address).

Additive and reversible (Rule 19). The backfill is deliberately *not*
reversed on downgrade: `email_verified` is also set legitimately by real
verifications, and a blanket reset to false on downgrade would discard
genuine verification state — a downgrade must never destroy data the
upgrade did not create.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c1e5a8d3f704"
down_revision = "b9d4f6a1c8e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "two_factor",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("secret", sa.Text(), nullable=False),
        sa.Column("backup_codes", sa.Text(), nullable=False),
        sa.Column(
            "user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("failed_verification_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_two_factor_secret"), "two_factor", ["secret"], unique=False)
    op.create_index(op.f("ix_two_factor_user_id"), "two_factor", ["user_id"], unique=False)

    op.add_column(
        "users",
        sa.Column(
            "two_factor_enabled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )

    # Grandfather every existing account — see the module docstring.
    op.execute("UPDATE users SET email_verified = true WHERE email_verified = false")


def downgrade() -> None:
    op.drop_column("users", "two_factor_enabled")
    op.drop_index(op.f("ix_two_factor_user_id"), table_name="two_factor")
    op.drop_index(op.f("ix_two_factor_secret"), table_name="two_factor")
    op.drop_table("two_factor")
