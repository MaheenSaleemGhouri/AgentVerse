"""add marketplace installs and the platform-admin roster

Revision ID: c83f6b21e7d4
Revises: b72e4d10a9c5
Create Date: 2026-08-06

Two tables with quite different tenancy, worth stating together because
the contrast is the point.

`marketplace_installs` is an ordinary tenant-owned table: `workspace_id`
non-null, FK to `workspaces`, leading its index, every query scoped by
it. The catalog's public-read exception (see `b72e4d10a9c5`) stops at the
catalog — a workspace's install history is nobody else's business.

`platform_admins` is one of Rule 11's explicit global exemptions,
alongside `users` and platform feature flags. It exists because
moderating the marketplace is a judgement about a listing owned by a
*different* workspace, which no workspace role can express; routing it
through the role hierarchy would have let a publisher approve
themselves. It is seeded empty and granted out of band — there is no
grant endpoint, so the set of people who can publish a listing to every
customer changes only through a reviewed, recorded action.

`marketplace_installs.agent_id` deliberately carries **no** foreign key
and is nullable: agents are deletable and the provenance record outlives
them. A dangling id means the installer removed their copy, not that the
install never happened. `listing_id` is ON DELETE RESTRICT for the same
reason the listing table's own workspace FK is — the row is what makes
an install explicable.

Additive and reversible. Code at the previous revision has neither
table, so a rollback loses install provenance and the admin roster, and
nothing else.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c83f6b21e7d4"
down_revision = "b72e4d10a9c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marketplace_installs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "listing_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("marketplace_listings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        # No FK, nullable: the agent may be deleted and this record
        # outlives it.
        sa.Column("agent_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("installed_by_user_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("version_number > 0", name="ck_marketplace_installs_version_positive"),
    )
    op.create_index(
        "ix_marketplace_installs_workspace_id", "marketplace_installs", ["workspace_id"]
    )
    op.create_index("ix_marketplace_installs_listing_id", "marketplace_installs", ["listing_id"])
    # One record per (workspace, listing, version): a double-clicked
    # install cannot produce two agents, while installing a *newer*
    # version still records separately — the difference between a retry
    # and an upgrade. A unique index rather than an application check,
    # because two concurrent installs would both pass a check and the
    # loser would fail after having already created an agent.
    op.create_index(
        "uq_marketplace_installs_version",
        "marketplace_installs",
        ["workspace_id", "listing_id", "version_number"],
        unique=True,
    )
    # The tenant-scoped list view, leading with `workspace_id` per §8.
    op.create_index(
        "ix_marketplace_installs_workspace",
        "marketplace_installs",
        ["workspace_id", "created_at"],
    )

    op.create_table(
        "platform_admins",
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        # Why this person has it — read during an incident review, when
        # "who could have approved this, and why did they have that
        # power" is the question being asked.
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("platform_admins")
    op.drop_table("marketplace_installs")
