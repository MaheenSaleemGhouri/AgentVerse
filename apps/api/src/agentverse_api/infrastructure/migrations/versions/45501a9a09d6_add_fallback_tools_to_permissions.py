"""add fallback_tools to permissions

Revision ID: 45501a9a09d6
Revises: c4e81f3d9b27
Create Date: 2026-07-30

Closes Phase 6 gap #2 (`docs/PHASE-6-MCP-CHECKLIST.md`): "no fallback
tool ... needs a notion of tool equivalence that does not exist yet."
This is that notion — a workspace admin's own mapping of one tool name
to another on the same installed server, never inferred by AgentVerse,
which has no way to verify two third-party tools are actually
interchangeable.

Additive: a nullable-by-default `jsonb` column with an empty-object
default, so every existing permission row is unaffected and every
pre-migration caller of `ToolGrant` behaves exactly as before (Rule 19).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "45501a9a09d6"
down_revision = "c4e81f3d9b27"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "permissions",
        sa.Column(
            "fallback_tools",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("permissions", "fallback_tools")
