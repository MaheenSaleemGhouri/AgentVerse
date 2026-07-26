"""phase 4: agents, agent_versions, agent_runs, agent_run_steps

Revision ID: 4387a581c5e4
Revises: dcc26fa22f2c
Create Date: 2026-07-26 15:03:53.091953
"""

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "4387a581c5e4"
down_revision: Union[str, None] = "dcc26fa22f2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- agents -----------------------------------------------------
    # `published_version_id` has no FK yet: `agent_versions` doesn't
    # exist until the next statement. The constraint is added below
    # once it does (a genuine circular reference between the two
    # tables, resolved by ordering, not by making anything nullable
    # that shouldn't be).
    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "active", "archived", name="agent_status"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("published_version_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("created_by_user_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agents_workspace_id"), "agents", ["workspace_id"], unique=False)
    op.create_index(
        "ix_agents_workspace_created", "agents", ["workspace_id", "created_at"], unique=False
    )

    # --- agent_versions -----------------------------------------------
    op.create_table(
        "agent_versions",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_user_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "version_number", name="uq_agent_version"),
    )
    op.create_index(
        op.f("ix_agent_versions_agent_id"), "agent_versions", ["agent_id"], unique=False
    )

    # Now that agent_versions exists, close the circular reference.
    op.create_foreign_key(
        "fk_agents_published_version",
        "agents",
        "agent_versions",
        ["published_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- agent_runs -----------------------------------------------------
    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("agent_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "success", "error", "cancelled", name="run_status"),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("cost_micro_usd", sa.BigInteger(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        # RESTRICT, not CASCADE: a run is a durable record of what
        # actually executed — the version it ran against must not
        # silently disappear out from under an audit trail.
        sa.ForeignKeyConstraint(["agent_version_id"], ["agent_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_runs_workspace_id"), "agent_runs", ["workspace_id"], unique=False
    )
    op.create_index(op.f("ix_agent_runs_agent_id"), "agent_runs", ["agent_id"], unique=False)
    # Leading-workspace_id composite index (CLAUDE.md §8): "recent runs
    # in this workspace" is the dashboard's actual query pattern.
    op.create_index(
        "ix_agent_runs_workspace_created",
        "agent_runs",
        ["workspace_id", sa.text("created_at DESC")],
        unique=False,
    )
    # Partial index for "currently active runs" — CLAUDE.md §8's own
    # named example of this pattern.
    op.create_index(
        "ix_agent_runs_active",
        "agent_runs",
        ["workspace_id"],
        unique=False,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    # Partial UNIQUE index, not just an app-level check: the idempotent
    # run-submission guarantee (CLAUDE.md §7) must hold even under a
    # genuine race, which only a DB constraint can enforce. Partial
    # because most runs (ad hoc "test" clicks in the builder) carry no
    # Idempotency-Key at all.
    op.create_index(
        "uq_agent_runs_workspace_idempotency_key",
        "agent_runs",
        ["workspace_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # --- agent_run_steps (partitioned by created_at) ---------------------
    # CLAUDE.md §5 names this table explicitly as needing partitioning
    # from its first migration. Postgres requires the partition key in
    # every primary/unique key on a partitioned table — hence the
    # composite (id, created_at) primary key instead of `id` alone.
    op.create_table(
        "agent_run_steps",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "step_type",
            sa.Enum(
                "run_started",
                "llm_call",
                "tool_call",
                "run_completed",
                "run_failed",
                name="run_step_type",
            ),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cost_micro_usd", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", "created_at"),
        postgresql_partition_by="RANGE (created_at)",
    )
    op.create_index(op.f("ix_agent_run_steps_run_id"), "agent_run_steps", ["run_id"], unique=False)
    op.create_index(
        op.f("ix_agent_run_steps_workspace_id"), "agent_run_steps", ["workspace_id"], unique=False
    )
    # A single catch-all DEFAULT partition for this phase — real
    # time-bounded partition rotation (e.g. monthly, created ahead of
    # time by a scheduled maintenance job) is a `postgresql-expert`
    # follow-up once real run volume exists, not built speculatively now.
    op.execute("CREATE TABLE agent_run_steps_default PARTITION OF agent_run_steps DEFAULT")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_run_steps_default")
    op.drop_index(op.f("ix_agent_run_steps_workspace_id"), table_name="agent_run_steps")
    op.drop_index(op.f("ix_agent_run_steps_run_id"), table_name="agent_run_steps")
    op.drop_table("agent_run_steps")
    sa.Enum(
        "run_started",
        "llm_call",
        "tool_call",
        "run_completed",
        "run_failed",
        name="run_step_type",
    ).drop(op.get_bind(), checkfirst=True)

    op.drop_index("uq_agent_runs_workspace_idempotency_key", table_name="agent_runs")
    op.drop_index("ix_agent_runs_active", table_name="agent_runs")
    op.drop_index("ix_agent_runs_workspace_created", table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_agent_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_workspace_id"), table_name="agent_runs")
    op.drop_table("agent_runs")
    sa.Enum("queued", "running", "success", "error", "cancelled", name="run_status").drop(
        op.get_bind(), checkfirst=True
    )

    op.drop_constraint("fk_agents_published_version", "agents", type_="foreignkey")
    op.drop_index(op.f("ix_agent_versions_agent_id"), table_name="agent_versions")
    op.drop_table("agent_versions")

    op.drop_index("ix_agents_workspace_created", table_name="agents")
    op.drop_index(op.f("ix_agents_workspace_id"), table_name="agents")
    op.drop_table("agents")
    sa.Enum("draft", "active", "archived", name="agent_status").drop(op.get_bind(), checkfirst=True)
