"""phase 10: workflows, workflow_versions, workflow_nodes, workflow_edges, workflow_runs, workflow_node_runs

Revision ID: 0958619d3576
Revises: 5aceb34e3a0f
Create Date: 2026-08-17 20:45:03.451279

DAG workflow automation (docs/roadmap.md Phase 10, docs/adr/0016).
Mirrors the `agents`/`agent_versions`/`agent_runs`/`agent_run_steps`
split, normalized rather than a single JSONB blob so nodes carry real
foreign keys to `agents`/`teams` — that is what makes "a workflow node
delegates to Phase 9, never reimplements it" a structural, DB-enforced
guarantee rather than only a code-review rule.

`status`/`type` columns are TEXT + CHECK, not a Postgres ENUM — this
repo's standing preference (see `f7d2c8b3a604`'s docstring): `ALTER TYPE
... DROP VALUE` does not exist, and Phase 4's `run_step_type` ENUM
already needed a follow-up migration just to add one value.

`workflow_node_runs` is partitioned by `created_at` from this, its first
migration — the per-node execution trail on a DAG run is this phase's
highest-volume table, same treatment as `agent_run_steps`/
`execution_events`.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0958619d3576"
down_revision: Union[str, None] = "5aceb34e3a0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- workflows --------------------------------------------------
    # `published_version_id` has no FK yet: `workflow_versions` doesn't
    # exist until the next statement — same circular-reference ordering
    # as `agents.published_version_id`.
    op.create_table(
        "workflows",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("published_version_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("created_by_user_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'archived')", name="ck_workflows_status"
        ),
    )
    op.create_index(op.f("ix_workflows_workspace_id"), "workflows", ["workspace_id"], unique=False)
    op.create_index(
        "ix_workflows_workspace_created", "workflows", ["workspace_id", "created_at"], unique=False
    )

    # --- workflow_versions --------------------------------------------
    op.create_table(
        "workflow_versions",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id", "version_number", name="uq_workflow_version"),
    )
    op.create_index(
        op.f("ix_workflow_versions_workflow_id"), "workflow_versions", ["workflow_id"], unique=False
    )

    # Now that workflow_versions exists, close the circular reference.
    op.create_foreign_key(
        "fk_workflows_published_version",
        "workflows",
        "workflow_versions",
        ["published_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- workflow_nodes ------------------------------------------------
    # `id` is caller-supplied (canvas-assigned), not server-generated —
    # an edge must reference a node before the version row exists.
    op.create_table(
        "workflow_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workflow_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("position_x", sa.Float(), nullable=False, server_default="0"),
        sa.Column("position_y", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        # RESTRICT: deleting an agent/team a published workflow depends
        # on must fail loudly rather than leaving a node that can never
        # run — same rule as `team_members.agent_id`.
        sa.Column("agent_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.ForeignKeyConstraint(
            ["workflow_version_id"], ["workflow_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(type = 'agent_step' AND agent_id IS NOT NULL AND team_id IS NULL) OR "
            "(type = 'team_step' AND team_id IS NOT NULL AND agent_id IS NULL) OR "
            "(type NOT IN ('agent_step', 'team_step') AND agent_id IS NULL AND team_id IS NULL)",
            name="ck_workflow_nodes_target",
        ),
    )
    op.create_index(
        op.f("ix_workflow_nodes_workflow_version_id"),
        "workflow_nodes",
        ["workflow_version_id"],
        unique=False,
    )

    # --- workflow_edges ------------------------------------------------
    op.create_table(
        "workflow_edges",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workflow_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("from_node_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("to_node_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("condition", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("branch_order", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["workflow_version_id"], ["workflow_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["from_node_id"], ["workflow_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_node_id"], ["workflow_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_workflow_edges_workflow_version_id"),
        "workflow_edges",
        ["workflow_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_edges_from_node_id"), "workflow_edges", ["from_node_id"], unique=False
    )
    op.create_index(
        op.f("ix_workflow_edges_to_node_id"), "workflow_edges", ["to_node_id"], unique=False
    )

    # --- workflow_runs ---------------------------------------------------
    op.create_table(
        "workflow_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workflow_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("cost_micro_usd", sa.BigInteger(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        # RESTRICT, not CASCADE: a run is a durable record of what
        # actually executed — same rule as `agent_runs.agent_version_id`.
        sa.ForeignKeyConstraint(
            ["workflow_version_id"], ["workflow_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'success', 'error', 'cancelled', 'paused')",
            name="ck_workflow_runs_status",
        ),
    )
    op.create_index(
        op.f("ix_workflow_runs_workspace_id"), "workflow_runs", ["workspace_id"], unique=False
    )
    op.create_index(
        op.f("ix_workflow_runs_workflow_id"), "workflow_runs", ["workflow_id"], unique=False
    )
    op.create_index(
        "ix_workflow_runs_workspace_created",
        "workflow_runs",
        ["workspace_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_workflow_runs_active",
        "workflow_runs",
        ["workspace_id"],
        unique=False,
        postgresql_where=sa.text("status IN ('queued', 'running', 'paused')"),
    )
    op.create_index(
        "uq_workflow_runs_workflow_idempotency_key",
        "workflow_runs",
        ["workflow_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # --- workflow_node_runs (partitioned by created_at) -------------------
    op.create_table(
        "workflow_node_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workflow_run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("team_session_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("approval_decision", sa.Text(), nullable=True),
        sa.Column("approved_by_user_id", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        # RESTRICT: a node belongs to an immutable published version,
        # which never has rows deleted from under a run that referenced it.
        sa.ForeignKeyConstraint(["node_id"], ["workflow_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["team_session_id"], ["team_sessions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", "created_at"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'success', 'error', 'cancelled', 'skipped', "
            "'paused_for_approval')",
            name="ck_workflow_node_runs_status",
        ),
        sa.CheckConstraint(
            "approval_decision IS NULL OR approval_decision IN ('approved', 'rejected')",
            name="ck_workflow_node_runs_approval_decision",
        ),
        postgresql_partition_by="RANGE (created_at)",
    )
    op.create_index(
        "ix_workflow_node_runs_run_created",
        "workflow_node_runs",
        ["workflow_run_id", "created_at"],
        unique=False,
    )
    op.execute(
        "CREATE TABLE workflow_node_runs_default PARTITION OF workflow_node_runs DEFAULT"
    )


def downgrade() -> None:
    # Reverse creation order so foreign keys never block a drop.
    op.execute("DROP TABLE IF EXISTS workflow_node_runs_default")
    op.drop_index("ix_workflow_node_runs_run_created", table_name="workflow_node_runs")
    op.drop_table("workflow_node_runs")

    op.drop_index("uq_workflow_runs_workflow_idempotency_key", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_active", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workspace_created", table_name="workflow_runs")
    op.drop_index(op.f("ix_workflow_runs_workflow_id"), table_name="workflow_runs")
    op.drop_index(op.f("ix_workflow_runs_workspace_id"), table_name="workflow_runs")
    op.drop_table("workflow_runs")

    op.drop_index(op.f("ix_workflow_edges_to_node_id"), table_name="workflow_edges")
    op.drop_index(op.f("ix_workflow_edges_from_node_id"), table_name="workflow_edges")
    op.drop_index(op.f("ix_workflow_edges_workflow_version_id"), table_name="workflow_edges")
    op.drop_table("workflow_edges")

    op.drop_index(op.f("ix_workflow_nodes_workflow_version_id"), table_name="workflow_nodes")
    op.drop_table("workflow_nodes")

    op.drop_constraint("fk_workflows_published_version", "workflows", type_="foreignkey")
    op.drop_index(op.f("ix_workflow_versions_workflow_id"), table_name="workflow_versions")
    op.drop_table("workflow_versions")

    op.drop_index("ix_workflows_workspace_created", table_name="workflows")
    op.drop_index(op.f("ix_workflows_workspace_id"), table_name="workflows")
    op.drop_table("workflows")
