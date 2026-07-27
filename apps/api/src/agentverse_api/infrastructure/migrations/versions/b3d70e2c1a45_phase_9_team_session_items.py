"""phase 9: team_session_items (durable SDK Session backing store)

Revision ID: b3d70e2c1a45
Revises: a91f4c37bd08
Create Date: 2026-07-27

The OpenAI Agents SDK's `Session` protocol needs somewhere to keep
conversation items between turns. Its shipped defaults are in-memory or
SQLite, both of which silently lose state on a multi-instance worker
fleet the moment a follow-up turn lands on a different instance —
CLAUDE.md §4 rules that out explicitly.

This is an eighth table beyond the seven ADR-0009 enumerated, and the
addition is deliberate rather than drift. The alternatives were both
worse: storing items in `execution_events` would mix SDK-internal
conversation state into the trace stream the UI renders (and make
`pop_item` a delete against a partitioned trace table), while storing
them in `communication_logs` would pollute that table's typed
inter-agent vocabulary with raw model items. Conversation history is its
own concern with its own lifecycle, so it gets its own table.

Additive and reversible: nothing existing is altered, so a rollback to
`a91f4c37bd08` cannot break already-deployed code (Rule 19).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b3d70e2c1a45"
down_revision = "a91f4c37bd08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_session_items",
        # A database-generated identity rather than the UUID used
        # elsewhere, because this column carries ordering as well as
        # identity. `get_items` returns chronological order and
        # `pop_item` removes the most recent one; deriving that from a
        # writer-computed `sequence` would race between concurrent
        # branches, whereas an identity column is monotonic by
        # construction.
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        # Which member's conversation branch this item belongs to. Null
        # for the team-level branch (the orchestrator's own thread).
        # Sessions are per-agent because a parallel topology runs several
        # members concurrently and merging their turns into one history
        # would hand each of them the others' partial reasoning.
        sa.Column("agent_id", postgresql.UUID(as_uuid=False), nullable=True),
        # One `TResponseInputItem` verbatim. Stored as opaque JSONB: the
        # shape is the SDK's, and reinterpreting it here would couple
        # AgentVerse to SDK internals the pinned version is free to
        # change.
        sa.Column("item", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", "created_at"),
        postgresql_partition_by="RANGE (created_at)",
    )
    # The one query shape the Session protocol issues: every item for a
    # branch, newest first (`get_items` reverses; `pop_item` takes one).
    op.create_index(
        "ix_team_session_items_branch",
        "team_session_items",
        ["session_id", "agent_id", "id"],
    )
    op.create_index("ix_team_session_items_workspace", "team_session_items", ["workspace_id"])
    op.execute("CREATE TABLE team_session_items_default PARTITION OF team_session_items DEFAULT")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS team_session_items_default")
    op.drop_table("team_session_items")
