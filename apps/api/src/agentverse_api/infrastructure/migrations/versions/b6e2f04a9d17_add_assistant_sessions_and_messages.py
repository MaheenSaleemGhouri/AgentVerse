"""Add assistant_sessions and assistant_messages.

Purely additive: two new tables, no change to anything already deployed,
so a rollback to the previous image cannot break on it (CLAUDE.md
Rule 19). `downgrade()` drops them in dependency order and is tested.

Both tables are scoped by `workspace_id` through the session — the
message table carries no copy of it (see the model docstring for why).

Revision ID: b6e2f04a9d17
Revises: a1c7e35d9f84
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "b6e2f04a9d17"
down_revision: str | None = "a1c7e35d9f84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assistant_sessions",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # TEXT, matching `users.id` — issued by the auth provider, not a
        # UUID like every other id in this schema.
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_message_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_assistant_sessions_workspace_id", "assistant_sessions", ["workspace_id"])
    op.create_index("ix_assistant_sessions_user_id", "assistant_sessions", ["user_id"])
    # Serves the only list query: my sessions in this workspace, most
    # recently active first.
    op.create_index(
        "ix_assistant_sessions_owner",
        "assistant_sessions",
        ["workspace_id", "user_id", "last_message_at"],
    )

    op.create_table(
        "assistant_messages",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        # The ordering key. `created_at` cannot be it: `now()` is
        # transaction-start time, so rows written in one transaction tie
        # and fall back to comparing random UUIDs.
        sa.Column("seq", sa.BigInteger(), sa.Identity(), nullable=False, unique=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=False),
            sa.ForeignKey("assistant_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        # TEXT + CHECK rather than a Postgres ENUM: `ALTER TYPE ... DROP
        # VALUE` does not exist, so an enum would make this migration
        # irreversible in practice.
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_assistant_messages_role"),
    )
    op.create_index("ix_assistant_messages_session_id", "assistant_messages", ["session_id"])
    op.create_index("ix_assistant_messages_session", "assistant_messages", ["session_id", "seq"])


def downgrade() -> None:
    op.drop_index("ix_assistant_messages_session", table_name="assistant_messages")
    op.drop_index("ix_assistant_messages_session_id", table_name="assistant_messages")
    op.drop_table("assistant_messages")
    op.drop_index("ix_assistant_sessions_owner", table_name="assistant_sessions")
    op.drop_index("ix_assistant_sessions_user_id", table_name="assistant_sessions")
    op.drop_index("ix_assistant_sessions_workspace_id", table_name="assistant_sessions")
    op.drop_table("assistant_sessions")
