"""add resource_permissions table

Revision ID: b9d4f6a1c8e2
Revises: a7c3e9f2b1d4
Create Date: 2026-08-01

Increment 6: the four base workspace roles (owner/admin/member/viewer)
never grow past four values — Postgres ENUM values aren't cleanly
reversible to drop (Rule 19), and widening `workspace_role` would
silently change what every existing `require_role(Role.X)` call site
means (ADR-0004 forbids exactly this). Instead, this is a new, orthogonal
grant table: a `member` can hold `resource_type "billing", permission
"manage"` without their role floor changing at all.

`resource_type`/`permission` are plain TEXT, app-validated, not a
Postgres ENUM — the same reasoning already applied to `api_keys.scope`.

`resource_id` is a non-null TEXT defaulting to `""` (meaning "every
resource of this type"), not a nullable column — a nullable column in
the six-column unique constraint below would let Postgres accept
duplicate NULL-bearing rows (NULL is never equal to NULL in a UNIQUE
constraint), silently defeating the tuple-uniqueness this table exists
to enforce.

Additive and reversible (Rule 19): one new table, nothing existing
altered.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b9d4f6a1c8e2"
down_revision = "a7c3e9f2b1d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resource_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resource_type", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("principal_type", sa.Text(), nullable=False, server_default="user"),
        sa.Column(
            "principal_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("permission", sa.Text(), nullable=False),
        sa.Column(
            "granted_by_user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "resource_type",
            "resource_id",
            "principal_type",
            "principal_id",
            "permission",
            name="uq_resource_permission",
        ),
    )
    op.create_index(
        op.f("ix_resource_permissions_workspace_id"),
        "resource_permissions",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_resource_permissions_workspace_id"), table_name="resource_permissions"
    )
    op.drop_table("resource_permissions")
