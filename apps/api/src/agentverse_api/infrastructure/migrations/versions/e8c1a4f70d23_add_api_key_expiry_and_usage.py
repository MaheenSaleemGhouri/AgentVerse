"""add api key expiry and usage counter

Revision ID: e8c1a4f70d23
Revises: d5b3f8c2a916
Create Date: 2026-08-03

`api_keys.expires_at` (nullable — NULL means "never expires", which is
every key issued before this migration, so no existing credential is
invalidated by deploying it) and `api_keys.use_count`.

`expires_at` is enforced in the bearer-authentication query itself
rather than checked by callers afterwards, so an expired key is
indistinguishable from an unknown one and no future call site can
forget the check.

`use_count` gets a server_default of 0 so the NOT NULL constraint can be
added in one step on a table small enough for it (`api_keys` holds one
row per issued credential, not per request). The high-volume tables that
need the two-step add-then-backfill treatment are the run/usage tables,
not this one.

Additive and reversible (Rule 19). The downgrade drops both columns,
which loses expiry configuration — acceptable and non-breaking in the
rollback direction, because code at the previous revision never read
either column, and keys revert to the "never expires" behaviour they had
before.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e8c1a4f70d23"
down_revision = "d5b3f8c2a916"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "api_keys",
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
    )
    # Partial index: the security score asks only for active, never-expiring
    # keys, so indexing the whole table would be wasted work.
    op.create_index(
        "ix_api_keys_workspace_non_expiring",
        "api_keys",
        ["workspace_id"],
        postgresql_where=sa.text("revoked_at IS NULL AND expires_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_api_keys_workspace_non_expiring", table_name="api_keys")
    op.drop_column("api_keys", "use_count")
    op.drop_column("api_keys", "expires_at")
