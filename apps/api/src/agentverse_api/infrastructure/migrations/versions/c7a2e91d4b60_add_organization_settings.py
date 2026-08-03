"""add organization settings

Revision ID: c7a2e91d4b60
Revises: b3f7c1a9e582
Create Date: 2026-08-03

Organization-level profile and branding (logo, brand colour, custom
domain, website, support email, description).

Deliberately a second table rather than columns bolted onto
`organizations`: the profile is optional and mostly-null, and keeping it
1:1-on-demand means "never configured" (every pre-existing organization)
stays a real, readable state instead of a row full of NULLs on the
identity table itself. This mirrors `workspace_settings` exactly
(8d925c92da0a).

`custom_domain` is UNIQUE for the same reason it is on workspaces: a
domain must resolve to exactly one tenant.

Additive and reversible (Rule 19): one new table, nothing existing
altered, so a rollback to the previous revision cannot break deployed
code.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c7a2e91d4b60"
down_revision = "b3f7c1a9e582"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=False)


def upgrade() -> None:
    op.create_table(
        "organization_settings",
        sa.Column(
            "organization_id",
            _UUID,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("brand_color", sa.Text(), nullable=True),
        sa.Column("custom_domain", sa.Text(), nullable=True, unique=True),
        sa.Column("website_url", sa.Text(), nullable=True),
        sa.Column("support_email", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_by_user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("organization_settings")
