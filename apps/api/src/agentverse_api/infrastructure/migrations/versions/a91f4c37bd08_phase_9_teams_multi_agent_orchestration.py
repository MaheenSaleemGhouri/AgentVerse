"""phase 9: teams, team_members, team_sessions, handoffs, shared_memory,
communication_logs, execution_events

Revision ID: a91f4c37bd08
Revises: 56f9a66678b2
Create Date: 2026-07-27

Multi-agent orchestration schema, built over Phase 4's agents rather than
beside them — `team_members.agent_id` is a foreign key to `agents`, so an
agent's instructions/model/tools/knowledge apply unchanged inside a team.

`execution_events` is partitioned by `created_at` from this, its first
migration (CLAUDE.md §5 names high-volume trace tables explicitly),
matching what `agent_run_steps` already does.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a91f4c37bd08"
down_revision = "56f9a66678b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    team_topology = sa.Enum(
        "supervisor_worker",
        "planner_executor_critic",
        "sequential",
        "parallel",
        name="team_topology",
    )
    team_member_role = sa.Enum(
        "supervisor",
        "planner",
        "executor",
        "critic",
        "researcher",
        "coder",
        "writer",
        "worker",
        "aggregator",
        name="team_member_role",
    )
    team_session_status = sa.Enum(
        "queued", "running", "success", "error", "cancelled", name="team_session_status"
    )
    handoff_kind = sa.Enum("automatic", "manual", "conditional", "parallel", name="handoff_kind")
    memory_scope = sa.Enum("team", "session", "agent", name="memory_scope")
    communication_kind = sa.Enum(
        "task_request",
        "task_result",
        "context_share",
        "intermediate_result",
        "error_report",
        name="communication_kind",
    )

    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("topology", team_topology, nullable=False),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("max_turns", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("max_cost_micro_usd", sa.BigInteger(), nullable=False, server_default="1000000"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("shared_memory_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "shared_knowledge_base_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        # Text, not UUID: `users.id` is owned by the auth provider and is
        # a text id, unlike every AgentVerse-owned table's uuid PK.
        sa.Column(
            "created_by_user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Leading workspace_id on every tenant index (CLAUDE.md §8) — the
    # list query is always "this workspace's teams, newest first".
    op.create_index("ix_teams_workspace_created", "teams", ["workspace_id", "created_at"])

    op.create_table(
        "team_members",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # RESTRICT: deleting an agent a team depends on must fail loudly
        # rather than leaving a team that cannot run its own topology.
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("agents.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("role", team_member_role, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("handoff_description", sa.Text(), nullable=True),
        sa.Column("can_receive_handoff", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("team_id", "agent_id", name="uq_team_member_agent"),
    )
    op.create_index("ix_team_members_workspace", "team_members", ["workspace_id"])
    op.create_index("ix_team_members_team_position", "team_members", ["team_id", "position"])
    op.create_index("ix_team_members_agent", "team_members", ["agent_id"])

    op.create_table(
        "team_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", team_session_status, nullable=False, server_default="queued"),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cost_micro_usd", sa.BigInteger(), nullable=True),
        sa.Column("total_turns", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_team_sessions_workspace_created", "team_sessions", ["workspace_id", "created_at"]
    )
    op.create_index("ix_team_sessions_team_created", "team_sessions", ["team_id", "created_at"])
    # Partial index on the hot subset the runtime polls (CLAUDE.md §8) —
    # in-flight sessions are a tiny fraction of the table over time.
    op.create_index(
        "ix_team_sessions_active",
        "team_sessions",
        ["workspace_id", "status"],
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    # Idempotency (Rule 14): replaying a submission must not start — or
    # bill for — a second run of the same team.
    op.create_index(
        "uq_team_sessions_idempotency",
        "team_sessions",
        ["team_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "handoffs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("team_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_agent_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "to_agent_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", handoff_kind, nullable=False),
        # The typed HandoffContract payload — summary + pointers, never a
        # raw transcript dump (CLAUDE.md §4).
        sa.Column("contract", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_handoffs_workspace", "handoffs", ["workspace_id"])
    op.create_index("ix_handoffs_session_sequence", "handoffs", ["session_id", "sequence"])

    op.create_table(
        "shared_memory",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("team_sessions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("scope", memory_scope, nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # Upsert target: writing the same key twice updates rather than
        # accumulating duplicates a reader would have to disambiguate.
        # Declared below as raw DDL rather than inline, because it needs
        # NULLS NOT DISTINCT — see the comment on the ALTER.
    )
    # `session_id` and `agent_id` are null for team-scoped entries, and
    # Postgres's default UNIQUE treats every NULL as distinct — which
    # would let the same team-scoped key be written twice and silently
    # turn the upsert into an append. NULLS NOT DISTINCT (Postgres 15+,
    # and this stack pins pg16) is what actually makes the constraint
    # mean what its name says.
    op.execute(
        "ALTER TABLE shared_memory ADD CONSTRAINT uq_shared_memory_scope_key "
        "UNIQUE NULLS NOT DISTINCT (team_id, session_id, agent_id, key)"
    )
    op.create_index("ix_shared_memory_workspace", "shared_memory", ["workspace_id"])
    op.create_index("ix_shared_memory_team_scope", "shared_memory", ["team_id", "scope"])
    op.create_index("ix_shared_memory_session", "shared_memory", ["session_id"])

    op.create_table(
        "communication_logs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("team_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_agent_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "to_agent_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", communication_kind, nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_communication_logs_workspace", "communication_logs", ["workspace_id"])
    op.create_index(
        "ix_communication_logs_session_sequence", "communication_logs", ["session_id", "sequence"]
    )

    # --- execution_events (partitioned by created_at) --------------------
    # Same treatment as agent_run_steps: a per-step trace stream on a
    # multi-agent run is the highest-volume table this phase adds, and
    # CLAUDE.md §8 requires partitioning from the first migration rather
    # than retrofitted later.
    op.create_table(
        "execution_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cost_micro_usd", sa.BigInteger(), nullable=True),
        # Postgres requires the partition key in every primary key on a
        # partitioned table — hence the composite, not a modeling choice.
        sa.PrimaryKeyConstraint("id", "created_at"),
        postgresql_partition_by="RANGE (created_at)",
    )
    op.create_index(
        "ix_execution_events_session_sequence", "execution_events", ["session_id", "sequence"]
    )
    op.create_index("ix_execution_events_workspace", "execution_events", ["workspace_id"])
    # A single catch-all DEFAULT partition for this phase — time-bounded
    # rotation created ahead of need is a later operational concern, and
    # matches what agent_run_steps already does.
    op.execute("CREATE TABLE execution_events_default PARTITION OF execution_events DEFAULT")


def downgrade() -> None:
    # Reverse creation order so foreign keys never block a drop.
    op.execute("DROP TABLE IF EXISTS execution_events_default")
    op.drop_table("execution_events")
    op.drop_table("communication_logs")
    op.drop_table("shared_memory")
    op.drop_table("handoffs")
    op.drop_table("team_sessions")
    op.drop_table("team_members")
    op.drop_table("teams")

    # Enums are dropped explicitly: Alembic's drop_table leaves the
    # Postgres type behind, and a re-run of upgrade() would then fail on
    # "type already exists" — which is exactly how a downgrade that
    # "worked" turns out to be untested.
    for enum_name in (
        "communication_kind",
        "memory_scope",
        "handoff_kind",
        "team_session_status",
        "team_member_role",
        "team_topology",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
