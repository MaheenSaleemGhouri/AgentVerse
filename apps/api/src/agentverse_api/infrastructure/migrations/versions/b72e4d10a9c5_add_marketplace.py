"""add the marketplace catalog, versions and reviews

Revision ID: b72e4d10a9c5
Revises: f0a4c9e21b58
Create Date: 2026-08-06

Four tables, and one deliberate departure from the platform's default
tenancy rule that is worth stating in the migration itself.

**The catalog is public.** Rule 11 makes `workspace_id` absolute for
tenant-owned tables. A marketplace listing carries
`publisher_workspace_id` so ownership is enforceable, but the catalog
index leads with `status`, not the tenant key — the dominant query is
"published listings in this category" across *every* workspace, and an
index leading with `workspace_id` could never serve it. Draft and
rejected listings remain private to their publisher; that is enforced in
`domain/listing.may_view` rather than by the index.

`marketplace_categories` is a lookup table rather than a CHECK
constraint because categories are editorial content that changes with
the catalog — adding one should be an INSERT, not a migration. Seeded
here with the initial set.

`marketplace_listing_versions.config` is an immutable snapshot.
Installing copies it; the publisher can then delete their source agent
and every existing install keeps working. `source_agent_version_id`
records provenance and deliberately carries **no foreign key**, because
the row it points at is allowed to disappear — an FK would either block
that deletion or null the provenance.

`publisher_workspace_id` is `ON DELETE RESTRICT`, not CASCADE: deleting
a workspace must not silently remove listings other workspaces have
installed from and reviewed. Withdrawing a listing is `unlisted`, which
is reversible and breaks nothing.

Additive and reversible. Code at the previous revision has no
marketplace, so a rollback loses only catalog content.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b72e4d10a9c5"
down_revision = "f0a4c9e21b58"
branch_labels = None
depends_on = None

_KINDS = "('agent', 'workflow')"
_STATUSES = "('draft', 'pending_review', 'published', 'rejected', 'unlisted')"

#: The initial category set. Seeded in the migration because a catalog
#: with no categories cannot accept its first listing — the FK requires
#: one — so this is not optional data.
_CATEGORIES: list[dict[str, object]] = [
    {
        "slug": "research",
        "name": "Research",
        "sort_order": 1,
        "description": "Agents that gather, summarise and cite sources.",
    },
    {
        "slug": "engineering",
        "name": "Engineering",
        "sort_order": 2,
        "description": "Code review, refactoring, debugging and repository automation.",
    },
    {
        "slug": "data",
        "name": "Data & analytics",
        "sort_order": 3,
        "description": "SQL, reporting and analysis over your own data.",
    },
    {
        "slug": "support",
        "name": "Customer support",
        "sort_order": 4,
        "description": "Triage, drafting replies and answering from a knowledge base.",
    },
    {
        "slug": "sales",
        "name": "Sales",
        "sort_order": 5,
        "description": "Prospecting, qualification and CRM automation.",
    },
    {
        "slug": "marketing",
        "name": "Marketing",
        "sort_order": 6,
        "description": "Content, campaigns and competitive research.",
    },
    {
        "slug": "operations",
        "name": "Operations",
        "sort_order": 7,
        "description": "Internal process automation, HR and finance workflows.",
    },
    {
        "slug": "productivity",
        "name": "Productivity",
        "sort_order": 8,
        "description": "Meetings, notes, scheduling and personal assistants.",
    },
]


def upgrade() -> None:
    op.create_table(
        "marketplace_categories",
        sa.Column("slug", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        # Editorial, not alphabetical: the order categories appear in is
        # a merchandising decision.
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.bulk_insert(
        sa.table(
            "marketplace_categories",
            sa.column("slug", sa.Text),
            sa.column("name", sa.Text),
            sa.column("description", sa.Text),
            sa.column("sort_order", sa.Integer),
        ),
        _CATEGORIES,
    )

    op.create_table(
        "marketplace_listings",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        # The public URL. Set once at creation — changing it breaks every
        # link anyone has shared.
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False, server_default="agent"),
        sa.Column(
            "publisher_workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # Denormalized so a catalog page renders without joining a table
        # it has no other reason to read. A stale name on a public page
        # is cosmetic; the join is on every card of every page.
        sa.Column("publisher_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "category_slug",
            sa.Text(),
            sa.ForeignKey("marketplace_categories.slug", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("pricing", sa.Text(), nullable=False, server_default="free"),
        sa.Column("price_cents", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("rating_sum", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("rating_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("install_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("latest_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("moderation_note", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(f"kind IN {_KINDS}", name="ck_marketplace_listings_kind"),
        sa.CheckConstraint(f"status IN {_STATUSES}", name="ck_marketplace_listings_status"),
        sa.CheckConstraint(
            "pricing IN ('free', 'premium')", name="ck_marketplace_listings_pricing"
        ),
        sa.CheckConstraint("price_cents >= 0", name="ck_marketplace_listings_price"),
        # Without this a listing can claim to be free and still charge.
        sa.CheckConstraint(
            "(pricing = 'free' AND price_cents = 0) OR (pricing = 'premium' AND price_cents > 0)",
            name="ck_marketplace_listings_pricing_matches_price",
        ),
        sa.CheckConstraint(
            "rating_sum >= 0 AND rating_count >= 0 AND install_count >= 0",
            name="ck_marketplace_listings_counters_non_negative",
        ),
        # Catches an aggregate corrupted by a double-applied write, which
        # would otherwise render as an average above 5 on a public page.
        sa.CheckConstraint(
            "rating_sum <= rating_count * 5", name="ck_marketplace_listings_rating_bound"
        ),
        sa.UniqueConstraint("slug", name="uq_marketplace_listings_slug"),
    )
    op.create_index("ix_marketplace_listings_slug", "marketplace_listings", ["slug"])
    op.create_index(
        "ix_marketplace_listings_publisher_workspace_id",
        "marketplace_listings",
        ["publisher_workspace_id"],
    )
    op.create_index(
        "ix_marketplace_listings_category_slug", "marketplace_listings", ["category_slug"]
    )
    op.create_index("ix_marketplace_listings_status", "marketplace_listings", ["status"])
    # The catalog's dominant query. Leads with `status` because it spans
    # every workspace — see the module docstring.
    op.create_index(
        "ix_marketplace_listings_catalog",
        "marketplace_listings",
        ["status", "category_slug", "install_count"],
    )
    # The publisher's own view, which *is* tenant-scoped.
    op.create_index(
        "ix_marketplace_listings_publisher",
        "marketplace_listings",
        ["publisher_workspace_id", "updated_at"],
    )
    # Featured placement is a small hot subset; partial keeps the index
    # proportional to what it serves.
    op.create_index(
        "ix_marketplace_listings_featured",
        "marketplace_listings",
        ["install_count"],
        postgresql_where=sa.text("is_featured AND status = 'published'"),
    )

    op.create_table(
        "marketplace_listing_versions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "listing_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("marketplace_listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("changelog", sa.Text(), nullable=False, server_default=""),
        # No foreign key, deliberately: the row it points at is allowed
        # to disappear.
        sa.Column("source_agent_version_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_marketplace_listing_versions_listing_id",
        "marketplace_listing_versions",
        ["listing_id"],
    )
    op.create_index(
        "uq_marketplace_listing_versions_number",
        "marketplace_listing_versions",
        ["listing_id", "version_number"],
        unique=True,
    )
    op.create_index(
        "ix_marketplace_listing_versions_listing",
        "marketplace_listing_versions",
        ["listing_id", "created_at"],
    )

    op.create_table(
        "marketplace_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "listing_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("marketplace_listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reviewer_workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The workspace's name, not the individual's: a review appears on
        # a public page, and a person's name should not land there
        # because they clicked a button.
        sa.Column("reviewer_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "rating >= 1 AND rating <= 5", name="ck_marketplace_reviews_rating_scale"
        ),
    )
    op.create_index("ix_marketplace_reviews_listing_id", "marketplace_reviews", ["listing_id"])
    op.create_index(
        "ix_marketplace_reviews_reviewer_workspace_id",
        "marketplace_reviews",
        ["reviewer_workspace_id"],
    )
    # One review per workspace per listing — a unique index rather than
    # an application check, because two concurrent submissions would both
    # pass a check.
    op.create_index(
        "uq_marketplace_reviews_one_per_workspace",
        "marketplace_reviews",
        ["listing_id", "reviewer_workspace_id"],
        unique=True,
    )
    op.create_index(
        "ix_marketplace_reviews_listing_created",
        "marketplace_reviews",
        ["listing_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("marketplace_reviews")
    op.drop_table("marketplace_listing_versions")
    op.drop_table("marketplace_listings")
    op.drop_table("marketplace_categories")
