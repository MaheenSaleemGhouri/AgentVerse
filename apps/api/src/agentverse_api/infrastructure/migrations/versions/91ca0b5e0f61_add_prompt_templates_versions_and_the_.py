"""phase 8: prompt_templates, prompt_versions, golden examples and eval runs

Revision ID: 91ca0b5e0f61
Revises: 8c1d444558ec
Create Date: 2026-08-21

The eval harness (docs/roadmap.md PHASE 8, docs/adr — none dedicated,
scoped as an incremental application-layer feature over existing
infrastructure). Before this migration, AgentVerse's 11 first-party
marketplace starter templates' `system_instructions`
(`marketplace_service/domain/templates.py`) were Python string literals
with no version history and no eval gate — exactly what CLAUDE.md §4
forbids ("no prompt ships or changes without an eval run"). This is the
registry those prompts (and any future first-party/internal prompt) are
versioned and eval-gated through.

`status` on `prompt_versions` is TEXT + CHECK, not a Postgres ENUM —
this repo's standing preference since Phase 10's `0958619d3576` (`ALTER
TYPE ... DROP VALUE` doesn't exist).

Not workspace-owned: first-party prompts are platform content, the same
reasoning `marketplace_service/domain/templates.py`'s own
`PLATFORM_WORKSPACE_ID` precedent uses one layer up, at the marketplace-
listing layer this module's output eventually feeds.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "91ca0b5e0f61"
down_revision: Union[str, None] = "8c1d444558ec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prompt_templates",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_prompt_templates_slug", "prompt_templates", ["slug"], unique=True
    )

    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("prompt_template_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("system_instructions", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["prompt_template_id"], ["prompt_templates.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "prompt_template_id", "version_number", name="uq_prompt_versions_template_number"
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'archived')", name="ck_prompt_versions_status"
        ),
    )
    op.create_index(
        "ix_prompt_versions_template_id", "prompt_versions", ["prompt_template_id"]
    )
    # A template may have at most one active version at a time — the
    # database, not just `promote_prompt_version.py`, refuses two.
    op.create_index(
        "uq_prompt_versions_one_active_per_template",
        "prompt_versions",
        ["prompt_template_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "prompt_golden_examples",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("prompt_template_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("input", postgresql.JSONB(), nullable=False),
        sa.Column("rubric", sa.Text(), nullable=False),
        sa.Column("expectation", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["prompt_template_id"], ["prompt_templates.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "rubric IN ('schema', 'keyword', 'llm_judge')",
            name="ck_prompt_golden_examples_rubric",
        ),
    )
    op.create_index(
        "ix_prompt_golden_examples_template_id", "prompt_golden_examples", ["prompt_template_id"]
    )

    op.create_table(
        "prompt_eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("prompt_version_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("results", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"], ["prompt_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_prompt_eval_runs_version_started",
        "prompt_eval_runs",
        ["prompt_version_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_prompt_eval_runs_version_started", table_name="prompt_eval_runs")
    op.drop_table("prompt_eval_runs")

    op.drop_index(
        "ix_prompt_golden_examples_template_id", table_name="prompt_golden_examples"
    )
    op.drop_table("prompt_golden_examples")

    op.drop_index(
        "uq_prompt_versions_one_active_per_template", table_name="prompt_versions"
    )
    op.drop_index("ix_prompt_versions_template_id", table_name="prompt_versions")
    op.drop_table("prompt_versions")

    op.drop_index("ix_prompt_templates_slug", table_name="prompt_templates")
    op.drop_table("prompt_templates")
