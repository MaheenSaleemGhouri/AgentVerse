"""seed the first-party agent template library

Revision ID: d15a7c94b2e0
Revises: c83f6b21e7d4
Create Date: 2026-08-06

Twelve curated agent configurations, seeded as ordinary marketplace
listings published by a platform-owned workspace.

**Why data in a migration rather than a seed script.** These rows are
the template library — the feature is the content. A seed script that
staging ran and production did not would mean the two environments have
different products, and "did anyone run the script" is not a question a
release should have to answer. It is `bulk_insert`, reversible, and
scoped to rows this migration created.

**Why listings rather than a `templates` table.** A template is "a
curated agent configuration you can install in one click", which is
exactly what a listing already is. A parallel table would have meant a
second install path, a second version history and a second set of
tenancy rules to keep correct (Rule 3). Four flags on the existing row
carry the difference: the platform publisher workspace, `is_official`,
free pricing, and `published` written directly — approving our own
submission would be theatre.

**The platform workspace has no members, deliberately.** Nobody can
authenticate into it, so the publisher routes are unreachable for it and
a template can only change through a reviewed migration. Curation by
construction rather than by policy. Its id is fixed rather than
generated so this migration and `domain/templates.py` agree without a
lookup.

Adding `is_official` is additive with a `false` default, so every
existing listing keeps its meaning. The downgrade removes the column and
exactly the rows seeded here, leaving customer listings untouched.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from agentverse_api.marketplace_service.domain.templates import (
    PLATFORM_WORKSPACE_ID,
    PLATFORM_WORKSPACE_NAME,
    PLATFORM_WORKSPACE_SLUG,
    TEMPLATES,
)

revision = "d15a7c94b2e0"
down_revision = "c83f6b21e7d4"
branch_labels = None
depends_on = None


def _listing_id(slug: str) -> str:
    """A deterministic id per template slug.

    Derived rather than random so a rollback-then-reapply produces the
    same ids — an install recorded against a template must still point at
    the same listing afterwards.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"agentverse:marketplace:template:{slug}"))


def upgrade() -> None:
    op.add_column(
        "marketplace_listings",
        sa.Column(
            "is_official",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # The template library's own query: official listings, in editorial
    # order. Partial, because it is a dozen rows against a catalog that
    # is meant to grow to thousands.
    op.create_index(
        "ix_marketplace_listings_official",
        "marketplace_listings",
        ["category_slug", "title"],
        postgresql_where=sa.text("is_official AND status = 'published'"),
    )

    workspaces = sa.table(
        "workspaces",
        sa.column("id", postgresql.UUID(as_uuid=False)),
        sa.column("name", sa.Text),
        sa.column("slug", sa.Text),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        workspaces.insert().values(
            id=PLATFORM_WORKSPACE_ID,
            name=PLATFORM_WORKSPACE_NAME,
            slug=PLATFORM_WORKSPACE_SLUG,
            created_at=sa.func.now(),
        )
    )

    listings = sa.table(
        "marketplace_listings",
        sa.column("id", postgresql.UUID(as_uuid=False)),
        sa.column("slug", sa.Text),
        sa.column("kind", sa.Text),
        sa.column("publisher_workspace_id", postgresql.UUID(as_uuid=False)),
        sa.column("publisher_name", sa.Text),
        sa.column("title", sa.Text),
        sa.column("summary", sa.Text),
        sa.column("description", sa.Text),
        sa.column("category_slug", sa.Text),
        sa.column("status", sa.Text),
        sa.column("pricing", sa.Text),
        sa.column("price_cents", sa.BigInteger),
        sa.column("is_official", sa.Boolean),
        sa.column("latest_version", sa.Integer),
        sa.column("published_at", sa.DateTime(timezone=True)),
    )
    versions = sa.table(
        "marketplace_listing_versions",
        sa.column("id", postgresql.UUID(as_uuid=False)),
        sa.column("listing_id", postgresql.UUID(as_uuid=False)),
        sa.column("version_number", sa.Integer),
        sa.column("config", postgresql.JSONB),
        sa.column("changelog", sa.Text),
    )

    op.bulk_insert(
        listings,
        [
            {
                "id": _listing_id(template.slug),
                "slug": template.slug,
                "kind": "agent",
                "publisher_workspace_id": PLATFORM_WORKSPACE_ID,
                "publisher_name": PLATFORM_WORKSPACE_NAME,
                "title": template.title,
                "summary": template.summary,
                "description": template.description,
                "category_slug": template.category_slug,
                # Straight to published: moderation exists so the platform
                # can review *other people's* submissions.
                "status": "published",
                "pricing": "free",
                "price_cents": 0,
                "is_official": True,
                "latest_version": 1,
            }
            for template in TEMPLATES
        ],
    )
    # `published_at` set in a second statement so it is the database's
    # clock rather than the migration process's.
    op.execute(
        listings.update()
        .where(listings.c.publisher_workspace_id == PLATFORM_WORKSPACE_ID)
        .values(published_at=sa.func.now())
    )

    op.bulk_insert(
        versions,
        [
            {
                "id": str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"agentverse:marketplace:template-version:{template.slug}:1",
                    )
                ),
                "listing_id": _listing_id(template.slug),
                "version_number": 1,
                "config": template.to_config(),
                "changelog": "Initial template.",
            }
            for template in TEMPLATES
        ],
    )


def downgrade() -> None:
    # Deletes exactly the rows seeded above, by their deterministic ids,
    # so a customer listing can never be caught by this. Versions first:
    # the FK is CASCADE, but being explicit means the intent survives a
    # future change to that FK.
    template_ids = [_listing_id(template.slug) for template in TEMPLATES]
    # Built through typed table constructs rather than raw SQL so the
    # bound ids are sent as UUIDs. A text array against a `uuid` column
    # fails at the driver ("operator does not exist: uuid = text") — in
    # the downgrade, which is the path least likely to be exercised
    # before it is needed.
    versions = sa.table(
        "marketplace_listing_versions",
        sa.column("listing_id", postgresql.UUID(as_uuid=False)),
    )
    listings = sa.table(
        "marketplace_listings",
        sa.column("id", postgresql.UUID(as_uuid=False)),
    )
    workspaces = sa.table("workspaces", sa.column("id", postgresql.UUID(as_uuid=False)))

    op.execute(versions.delete().where(versions.c.listing_id.in_(template_ids)))
    op.execute(listings.delete().where(listings.c.id.in_(template_ids)))
    op.execute(workspaces.delete().where(workspaces.c.id == PLATFORM_WORKSPACE_ID))
    op.drop_index("ix_marketplace_listings_official", table_name="marketplace_listings")
    op.drop_column("marketplace_listings", "is_official")
