"""add support tickets

Revision ID: 5aceb34e3a0f
Revises: 936121adfffc
Create Date: 2026-08-14

Phase 11's dogfooded support-triage automation: a minimal ticket entity
distinct from `agent_runs` (a ticket has its own lifecycle a human can
review after the triage run completes — `agent_runs` has no concept of
that and shouldn't grow one for a single internal-tool consumer).

`status` is TEXT + CHECK, not a Postgres ENUM, matching this repo's
standing preference (see `f7d2c8b3a604`'s docstring) — `ALTER TYPE ...
DROP VALUE` does not exist, and this table's status set is exactly the
kind of thing likely to grow a value later.

`triage_run_id` references `agent_runs.id`, owned by `orchestration_
service` — read-only from this table's side (this migration writes no
column on `agent_runs`), the same "worker fleet + owning service share
one Postgres instance" exception `apps/worker`'s config docstring
already invokes for cross-context FKs within one deployable unit.

Additive and reversible: `downgrade()` drops the table cleanly.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "5aceb34e3a0f"
down_revision = "936121adfffc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="triaging"),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("priority", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Text(), nullable=True),
        sa.Column("draft_reply", sa.Text(), nullable=True),
        sa.Column("triage_run_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("created_by_user_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triage_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('triaging', 'triaged', 'resolved', 'failed')",
            name="ck_support_tickets_status",
        ),
    )
    # Leading workspace_id, matching CLAUDE.md §8's composite-index
    # convention — "recent tickets in this workspace" is the only real
    # query pattern this table serves.
    op.create_index(
        "ix_support_tickets_workspace_created",
        "support_tickets",
        ["workspace_id", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_support_tickets_workspace_created", table_name="support_tickets")
    op.drop_table("support_tickets")
