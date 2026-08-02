"""add workspace_ip_allowlist

Revision ID: d2f6b9e4a815
Revises: c1e5a8d3f704
Create Date: 2026-08-01

Increment 7.4: opt-in per-workspace IP restriction.

Empty = unrestricted. Every pre-existing workspace has zero rows and is
therefore completely unaffected — the enforcing dependency treats "no
rows configured" as "allow everything", not "deny everything". That
fail-open is correct *for this specific check*: an empty allowlist means
the feature was never turned on. (Note this is deliberately the opposite
of the rate-limiter's fail-closed-on-Redis-unavailable rule — there,
absence of data means a dependency broke; here, absence of data means an
admin never configured the feature.)

Additive and reversible (Rule 19): one new table, nothing existing
altered.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d2f6b9e4a815"
down_revision = "c1e5a8d3f704"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_ip_allowlist",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cidr", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "cidr", name="uq_workspace_ip_allowlist_cidr"),
    )
    op.create_index(
        op.f("ix_workspace_ip_allowlist_workspace_id"),
        "workspace_ip_allowlist",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_workspace_ip_allowlist_workspace_id"), table_name="workspace_ip_allowlist"
    )
    op.drop_table("workspace_ip_allowlist")
