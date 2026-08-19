"""Marketplace ORM models.

The tenancy shape here is the departure worth reading first: listings
carry `publisher_workspace_id` so ownership is enforceable, but the
catalog index deliberately leads with `status` rather than
`workspace_id`, because the dominant query is "published listings in
this category" across *every* workspace. Leading with `workspace_id`
would produce an index the catalog can never use.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from agentverse_api.infrastructure.orm_base import Base

#: Matches `kb_chunks.embedding` (Phase 5) — the shared
#: `OpenAIEmbeddingProvider` default dimension.
_EMBEDDING_DIM = 1536

_KINDS = "('agent', 'workflow')"
_STATUSES = "('draft', 'pending_review', 'published', 'rejected', 'unlisted')"


class MarketplaceCategoryModel(Base):
    """Curated categories.

    A lookup table rather than a CHECK constraint because marketplace
    categories are editorial content that changes with the catalog —
    `database-architect`'s rule for values that change often. Adding one
    should be an INSERT, not a migration.
    """

    __tablename__ = "marketplace_categories"

    slug: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    #: Editorial ordering for the category rail. Not alphabetical: the
    #: order categories are shown in is a merchandising decision.
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class MarketplaceListingModel(Base):
    """One published agent or workflow."""

    __tablename__ = "marketplace_listings"
    __table_args__ = (
        CheckConstraint(f"kind IN {_KINDS}", name="ck_marketplace_listings_kind"),
        CheckConstraint(f"status IN {_STATUSES}", name="ck_marketplace_listings_status"),
        CheckConstraint("pricing IN ('free', 'premium')", name="ck_marketplace_listings_pricing"),
        # Money is integer cents (Rule 15) and never negative — a
        # negative price would flow into a checkout as a credit.
        CheckConstraint("price_cents >= 0", name="ck_marketplace_listings_price"),
        # Free and premium must agree with the price. Without this a
        # listing can claim to be free and still charge.
        CheckConstraint(
            "(pricing = 'free' AND price_cents = 0) OR (pricing = 'premium' AND price_cents > 0)",
            name="ck_marketplace_listings_pricing_matches_price",
        ),
        CheckConstraint(
            "rating_sum >= 0 AND rating_count >= 0 AND install_count >= 0",
            name="ck_marketplace_listings_counters_non_negative",
        ),
        # A rating sum can never exceed 5 per review. Catches an
        # aggregate corrupted by a double-applied write, which would
        # otherwise show as an average above 5 on a public page.
        CheckConstraint(
            "rating_sum <= rating_count * 5", name="ck_marketplace_listings_rating_bound"
        ),
        # The catalog's dominant query: published listings, optionally in
        # a category, newest or most-installed first. Leads with `status`
        # rather than `workspace_id` because the catalog spans every
        # workspace — an index leading with the tenant key would be
        # unusable here.
        Index(
            "ix_marketplace_listings_catalog",
            "status",
            "category_slug",
            "install_count",
        ),
        # The publisher's own "my listings" view, which *is* tenant
        # scoped and does need the workspace-leading index.
        Index(
            "ix_marketplace_listings_publisher",
            "publisher_workspace_id",
            "updated_at",
        ),
        # Featured placement is a small, hot subset — partial so the
        # index stays proportional to what it serves.
        Index(
            "ix_marketplace_listings_featured",
            "install_count",
            postgresql_where="is_featured AND status = 'published'",
        ),
        # The template library's own query. Partial for the same reason:
        # a dozen rows against a catalog meant to grow to thousands.
        Index(
            "ix_marketplace_listings_official",
            "category_slug",
            "title",
            postgresql_where="is_official AND status = 'published'",
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Globally unique: it is the public URL. Changing it would break
    # every link anyone has shared, so it is set once at creation.
    slug: Mapped[str] = mapped_column(Text, unique=True, index=True)
    kind: Mapped[str] = mapped_column(Text, default="agent")
    publisher_workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        # RESTRICT, not CASCADE: deleting a workspace must not silently
        # remove listings other workspaces have installed from and
        # reviewed. Withdrawing a listing is `unlisted`, which is a
        # different, reversible action.
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        index=True,
    )
    # Denormalized from the workspace so a catalog page renders without
    # joining a table it has no other reason to read. Refreshed when the
    # listing is updated; a stale publisher name on a public page is a
    # cosmetic problem, where the join is on every card of every page.
    publisher_name: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    category_slug: Mapped[str] = mapped_column(
        Text,
        ForeignKey("marketplace_categories.slug", ondelete="RESTRICT"),
        index=True,
    )
    status: Mapped[str] = mapped_column(Text, default="draft", index=True)
    pricing: Mapped[str] = mapped_column(Text, default="free")
    price_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    rating_sum: Mapped[int] = mapped_column(BigInteger, default=0)
    rating_count: Mapped[int] = mapped_column(BigInteger, default=0)
    install_count: Mapped[int] = mapped_column(BigInteger, default=0)
    # Set by a platform admin, never by the publisher — otherwise every
    # publisher features themselves.
    is_featured: Mapped[bool] = mapped_column(default=False)
    # First-party: published by the platform workspace, always free, and
    # never moderated (approving our own submission would be theatre).
    # This is what the template library filters on — a template is an
    # ordinary listing with this flag, not a parallel system.
    is_official: Mapped[bool] = mapped_column(default=False)
    latest_version: Mapped[int] = mapped_column(Integer, default=0)
    # Why a submission was rejected. Shown to the publisher, so a
    # rejection is actionable rather than a dead end.
    moderation_note: Mapped[str | None] = mapped_column(Text, default=None)
    # Null until the listing is first approved/relisted — hybrid search
    # degrades to keyword-only for anything not yet embedded
    # (`hybrid_marketplace_search.py`). Travels with `embedding_model`/
    # `_version` so a similarity query never mixes vector spaces, same
    # discipline as `kb_chunks`.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(_EMBEDDING_DIM), default=None)
    embedding_model: Mapped[str | None] = mapped_column(Text, default=None)
    embedding_model_version: Mapped[str | None] = mapped_column(Text, default=None)
    published_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class MarketplaceListingVersionModel(Base):
    """An immutable published snapshot.

    Installing copies `config` into the installing workspace. The
    publisher can then delete their source agent, rewrite it, or leave
    the platform, and every existing install keeps working — which is
    the only way a marketplace can be trusted.

    `source_agent_version_id` records provenance and deliberately has
    **no foreign key**: the row it points at is allowed to disappear, and
    an FK would either block that deletion or null the provenance.
    """

    __tablename__ = "marketplace_listing_versions"
    __table_args__ = (
        Index(
            "uq_marketplace_listing_versions_number",
            "listing_id",
            "version_number",
            unique=True,
        ),
        Index("ix_marketplace_listing_versions_listing", "listing_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    listing_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("marketplace_listings.id", ondelete="CASCADE"),
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer)
    # The snapshot. Validated by an application-layer schema on read,
    # following the `agents.config` precedent (§8).
    config: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    changelog: Mapped[str] = mapped_column(Text, default="")
    source_agent_version_id: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class MarketplaceInstallModel(Base):
    """Provenance: which listing, at which version, became which agent.

    Unlike the catalog, this **is** a tenant-owned table and follows the
    ordinary rule — `workspace_id` leading, every query scoped by it. A
    workspace's install history is nobody else's business.

    Nothing reads back through this at run time. The installed agent is a
    copy of the snapshot and stands alone; this exists so a workspace can
    ask "where did this come from, and is there a newer version?", and so
    the catalog's denormalized install count can be reconciled against
    real rows.
    """

    __tablename__ = "marketplace_installs"
    __table_args__ = (
        # One record per (workspace, listing, version). A double-clicked
        # install therefore cannot produce two agents, while installing a
        # *newer* version still records separately — the difference
        # between a retry and an upgrade. A workspace that genuinely
        # wants two copies duplicates the installed agent, which is an
        # action in their own workspace rather than a second import.
        Index(
            "uq_marketplace_installs_version",
            "workspace_id",
            "listing_id",
            "version_number",
            unique=True,
        ),
        Index("ix_marketplace_installs_workspace", "workspace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    listing_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        # RESTRICT: the listing row is what makes an install explicable,
        # and a listing is withdrawn by unlisting rather than deleted.
        ForeignKey("marketplace_listings.id", ondelete="RESTRICT"),
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer)
    # No foreign key, and nullable: agents are deletable, and the
    # provenance record outlives them. A dangling id here means the
    # installer removed their copy, not that the install never happened.
    agent_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), default=None)
    installed_by_user_id: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class MarketplaceReviewModel(Base):
    """One workspace's review of one listing."""

    __tablename__ = "marketplace_reviews"
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_marketplace_reviews_rating_scale"),
        # One review per workspace per listing. Not per user: a
        # workspace with eight members could otherwise post eight
        # reviews, and the public average would be whatever the largest
        # team decided. A unique index rather than an application check,
        # because two concurrent submissions would both pass a check.
        Index(
            "uq_marketplace_reviews_one_per_workspace",
            "listing_id",
            "reviewer_workspace_id",
            unique=True,
        ),
        Index("ix_marketplace_reviews_listing_created", "listing_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    listing_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("marketplace_listings.id", ondelete="CASCADE"),
        index=True,
    )
    reviewer_workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    # The workspace's name, not the individual's: a review appears on a
    # public catalog page, and a person's name should not land there
    # because they happened to click the button.
    reviewer_name: Mapped[str] = mapped_column(Text, default="")
    rating: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
