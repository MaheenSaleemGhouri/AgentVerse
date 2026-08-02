"""add workspace settings

Revision ID: 8d925c92da0a
Revises: 45501a9a09d6
Create Date: 2026-07-30

Workspace-wide branding/policy (logo, brand color, custom domain,
retention/storage limits) — distinct from `settings/appearance`, which
is a personal, client-side light/dark theme toggle with no table at all.

1:1 with `workspaces`: `workspace_id` is both primary key and foreign
key, so at most one settings row per workspace, and a workspace with no
row (every pre-existing one) is a real, expected "no settings configured
yet" state rather than a data-integrity gap.

Additive and reversible (Rule 19): a new table only, nothing existing
altered.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "8d925c92da0a"
down_revision = "45501a9a09d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_settings",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("brand_color", sa.Text(), nullable=True),
        sa.Column("custom_domain", sa.Text(), nullable=True, unique=True),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("storage_limit_mb", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_by_user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("workspace_settings")
