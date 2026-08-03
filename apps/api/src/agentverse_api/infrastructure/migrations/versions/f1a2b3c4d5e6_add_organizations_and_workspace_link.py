"""add organizations and workspace link

Revision ID: f1a2b3c4d5e6
Revises: cc70c017a8d3
Create Date: 2026-08-01

Organizations are an additive, non-isolating grouping layer over
existing workspaces (ADR-0011): a single org groups N workspaces for
billing rollup / SSO config / branding only. `workspace_id` remains the
sole tenant-isolation boundary (Rule 11) — attaching a workspace to an
organization grants zero implicit access; `workspace_members` is never
read or written by anything in this migration or the code it supports.

`workspaces.organization_id` is nullable with `ON DELETE SET NULL`:
deleting an organization detaches its workspaces, never cascade-deletes
them. `organization_members` is a new table paralleling
`workspace_members`, reusing the existing `workspace_role` Postgres ENUM
type (`create_type=False` — the type already exists) rather than
defining a second, near-identical one (DRY, CLAUDE.md §16).

`audit_logs.organization_id` is nullable with `ON DELETE SET NULL`, for
organization-level events (e.g. `organization.created`) that have no
single workspace to attribute to.

Additive and reversible (Rule 19): two new tables and two new nullable
columns, nothing existing altered or dropped.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f1a2b3c4d5e6"
down_revision = "cc70c017a8d3"
branch_labels = None
depends_on = None

_WORKSPACE_ROLE = postgresql.ENUM(
    "owner", "admin", "member", "viewer", name="workspace_role", create_type=False
)


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_organizations_slug"), "organizations", ["slug"], unique=True)

    op.create_table(
        "organization_members",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("role", _WORKSPACE_ROLE, nullable=False),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_organization_member"),
    )
    op.create_index(
        op.f("ix_organization_members_organization_id"),
        "organization_members",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_members_user_id"),
        "organization_members",
        ["user_id"],
        unique=False,
    )

    op.add_column(
        "workspaces",
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_workspaces_organization_id"), "workspaces", ["organization_id"], unique=False
    )

    op.add_column(
        "audit_logs",
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_audit_logs_organization_id"), "audit_logs", ["organization_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_logs_organization_id"), table_name="audit_logs")
    op.drop_column("audit_logs", "organization_id")

    op.drop_index(op.f("ix_workspaces_organization_id"), table_name="workspaces")
    op.drop_column("workspaces", "organization_id")

    op.drop_index(op.f("ix_organization_members_user_id"), table_name="organization_members")
    op.drop_index(
        op.f("ix_organization_members_organization_id"), table_name="organization_members"
    )
    op.drop_table("organization_members")

    op.drop_index(op.f("ix_organizations_slug"), table_name="organizations")
    op.drop_table("organizations")
