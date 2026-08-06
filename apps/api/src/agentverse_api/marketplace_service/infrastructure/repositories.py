"""Postgres adapters for the marketplace context."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import UnaryExpression, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.marketplace_service.domain.listing import (
    Listing,
    ListingKind,
    ListingStatus,
    Pricing,
)
from agentverse_api.marketplace_service.domain.ports import Category, ListingVersion
from agentverse_api.marketplace_service.domain.review import RatingAggregate, Review
from agentverse_api.marketplace_service.infrastructure.models import (
    MarketplaceCategoryModel,
    MarketplaceListingModel,
    MarketplaceListingVersionModel,
    MarketplaceReviewModel,
)

#: Catalog sort orders. A closed set: `sort` arrives from a query string,
#: and interpolating it into an ORDER BY would be an injection point.
#: Mapping a name to a column here means an unknown value falls back to
#: the default rather than reaching SQL.
_SORTS: dict[str, UnaryExpression[Any]] = {
    "popular": MarketplaceListingModel.install_count.desc(),
    "newest": MarketplaceListingModel.published_at.desc().nullslast(),
    "rating": MarketplaceListingModel.rating_sum.desc(),
    "name": MarketplaceListingModel.title.asc(),
}
DEFAULT_SORT = "popular"


async def _flush_and_reload(session: AsyncSession, row: MarketplaceListingModel) -> None:
    """Flush a mutation, then read back what the database generated.

    `updated_at` carries an `onupdate`, so SQLAlchemy expires it after an
    UPDATE and would otherwise try to reload it lazily at attribute
    access — synchronous IO in an async context, which raises
    `MissingGreenlet`. The refresh is one explicit SELECT instead of an
    implicit one that cannot work here.
    """
    await session.flush()
    await session.refresh(row)


def _to_listing(row: MarketplaceListingModel) -> Listing:
    return Listing(
        id=row.id,
        slug=row.slug,
        kind=ListingKind(row.kind),
        publisher_workspace_id=row.publisher_workspace_id,
        publisher_name=row.publisher_name,
        title=row.title,
        summary=row.summary,
        description=row.description,
        category_slug=row.category_slug,
        status=ListingStatus(row.status),
        pricing=Pricing(row.pricing),
        price_cents=row.price_cents,
        rating_sum=row.rating_sum,
        rating_count=row.rating_count,
        install_count=row.install_count,
        is_featured=row.is_featured,
        latest_version=row.latest_version,
        published_at=row.published_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlListingRepository:
    """Implements `domain.ports.ListingRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def browse(
        self,
        *,
        category_slug: str | None,
        kind: ListingKind | None,
        query: str | None,
        featured_only: bool,
        free_only: bool,
        sort: str,
        limit: int,
        offset: int,
    ) -> tuple[list[Listing], int]:
        # The one read in this context with no workspace filter. A
        # published listing is public — see the module docstring on
        # `domain/listing.py`. The status filter is what keeps drafts
        # and rejections out, and it is not optional.
        conditions = [MarketplaceListingModel.status == ListingStatus.PUBLISHED.value]
        if category_slug:
            conditions.append(MarketplaceListingModel.category_slug == category_slug)
        if kind is not None:
            conditions.append(MarketplaceListingModel.kind == kind.value)
        if featured_only:
            conditions.append(MarketplaceListingModel.is_featured.is_(True))
        if free_only:
            conditions.append(MarketplaceListingModel.pricing == Pricing.FREE.value)
        if query:
            # `ilike` over title and summary. Deliberately not full-text
            # search: that needs a tsvector column and an index to be
            # worth anything, and building one before the catalog has
            # content would be tuning against no data. M6's search work
            # owns the upgrade; this is honest until then.
            pattern = f"%{query.strip()}%"
            conditions.append(
                or_(
                    MarketplaceListingModel.title.ilike(pattern),
                    MarketplaceListingModel.summary.ilike(pattern),
                )
            )

        total = await self._session.execute(
            select(func.count()).select_from(MarketplaceListingModel).where(*conditions)
        )
        rows = await self._session.execute(
            select(MarketplaceListingModel)
            .where(*conditions)
            .order_by(_SORTS.get(sort, _SORTS[DEFAULT_SORT]))
            .limit(limit)
            .offset(offset)
        )
        return [_to_listing(row) for row in rows.scalars().all()], int(total.scalar_one())

    async def get_by_slug(self, slug: str) -> Listing | None:
        result = await self._session.execute(
            select(MarketplaceListingModel).where(MarketplaceListingModel.slug == slug)
        )
        row = result.scalar_one_or_none()
        return None if row is None else _to_listing(row)

    async def get_by_id(self, listing_id: str) -> Listing | None:
        result = await self._session.execute(
            select(MarketplaceListingModel).where(MarketplaceListingModel.id == listing_id)
        )
        row = result.scalar_one_or_none()
        return None if row is None else _to_listing(row)

    async def list_for_publisher(self, *, publisher_workspace_id: str, limit: int) -> list[Listing]:
        result = await self._session.execute(
            select(MarketplaceListingModel)
            .where(MarketplaceListingModel.publisher_workspace_id == publisher_workspace_id)
            .order_by(MarketplaceListingModel.updated_at.desc())
            .limit(limit)
        )
        return [_to_listing(row) for row in result.scalars().all()]

    async def create(
        self,
        *,
        slug: str,
        kind: ListingKind,
        publisher_workspace_id: str,
        publisher_name: str,
        title: str,
        summary: str,
        description: str,
        category_slug: str,
        pricing: Pricing,
        price_cents: int,
    ) -> Listing:
        row = MarketplaceListingModel(
            id=str(uuid.uuid4()),
            slug=slug,
            kind=kind.value,
            publisher_workspace_id=publisher_workspace_id,
            publisher_name=publisher_name,
            title=title,
            summary=summary,
            description=description,
            category_slug=category_slug,
            status=ListingStatus.DRAFT.value,
            pricing=pricing.value,
            price_cents=price_cents,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_listing(row)

    async def update_details(
        self,
        *,
        listing_id: str,
        title: str | None,
        summary: str | None,
        description: str | None,
        category_slug: str | None,
        pricing: Pricing | None,
        price_cents: int | None,
    ) -> Listing:
        result = await self._session.execute(
            select(MarketplaceListingModel).where(MarketplaceListingModel.id == listing_id)
        )
        row = result.scalar_one()
        # `slug` is deliberately absent: it is the public URL, and
        # changing it would break every link anyone has shared.
        if title is not None:
            row.title = title
        if summary is not None:
            row.summary = summary
        if description is not None:
            row.description = description
        if category_slug is not None:
            row.category_slug = category_slug
        if pricing is not None:
            row.pricing = pricing.value
        if price_cents is not None:
            row.price_cents = price_cents
        await _flush_and_reload(self._session, row)
        return _to_listing(row)

    async def set_status(
        self,
        *,
        listing_id: str,
        status: ListingStatus,
        moderation_note: str | None = None,
    ) -> Listing:
        result = await self._session.execute(
            select(MarketplaceListingModel).where(MarketplaceListingModel.id == listing_id)
        )
        row = result.scalar_one()
        row.status = status.value
        row.moderation_note = moderation_note
        if status is ListingStatus.PUBLISHED and row.published_at is None:
            # Set once. A listing that is unlisted and republished keeps
            # its original publication date — "published 2 years ago" is
            # a fact about the listing, not about the last toggle.
            row.published_at = datetime.now(UTC)
        await _flush_and_reload(self._session, row)
        return _to_listing(row)

    async def set_featured(self, *, listing_id: str, is_featured: bool) -> Listing:
        result = await self._session.execute(
            select(MarketplaceListingModel).where(MarketplaceListingModel.id == listing_id)
        )
        row = result.scalar_one()
        row.is_featured = is_featured
        await _flush_and_reload(self._session, row)
        return _to_listing(row)

    async def record_install(self, listing_id: str) -> None:
        # Incremented in SQL, not read-modify-written: two concurrent
        # installs would otherwise both read the same count, and the
        # catalog sorts by this number.
        await self._session.execute(
            update(MarketplaceListingModel)
            .where(MarketplaceListingModel.id == listing_id)
            .values(install_count=MarketplaceListingModel.install_count + 1)
        )

    async def set_rating_aggregate(self, *, listing_id: str, aggregate: RatingAggregate) -> None:
        await self._session.execute(
            update(MarketplaceListingModel)
            .where(MarketplaceListingModel.id == listing_id)
            .values(rating_sum=aggregate.rating_sum, rating_count=aggregate.rating_count)
        )

    async def slug_exists(self, slug: str) -> bool:
        result = await self._session.execute(
            select(MarketplaceListingModel.id).where(MarketplaceListingModel.slug == slug)
        )
        return result.scalar_one_or_none() is not None


def _to_version(row: MarketplaceListingVersionModel) -> ListingVersion:
    return ListingVersion(
        id=row.id,
        listing_id=row.listing_id,
        version_number=row.version_number,
        config=row.config or {},
        changelog=row.changelog,
        source_agent_version_id=row.source_agent_version_id,
        created_at=row.created_at.isoformat(),
    )


class SqlListingVersionRepository:
    """Implements `domain.ports.ListingVersionRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def publish_version(
        self,
        *,
        listing_id: str,
        version_number: int,
        config: dict[str, object],
        changelog: str,
        source_agent_version_id: str | None,
    ) -> ListingVersion:
        row = MarketplaceListingVersionModel(
            id=str(uuid.uuid4()),
            listing_id=listing_id,
            version_number=version_number,
            config=config,
            changelog=changelog,
            source_agent_version_id=source_agent_version_id,
        )
        self._session.add(row)
        # The listing's `latest_version` moves with it, in the same
        # transaction: a listing pointing at a version that does not
        # exist would make install fail for everyone.
        await self._session.execute(
            update(MarketplaceListingModel)
            .where(MarketplaceListingModel.id == listing_id)
            .values(latest_version=version_number)
        )
        await self._session.flush()
        return _to_version(row)

    async def list_versions(self, listing_id: str) -> list[ListingVersion]:
        result = await self._session.execute(
            select(MarketplaceListingVersionModel)
            .where(MarketplaceListingVersionModel.listing_id == listing_id)
            .order_by(MarketplaceListingVersionModel.version_number.desc())
        )
        return [_to_version(row) for row in result.scalars().all()]

    async def get_version(
        self, *, listing_id: str, version_number: int | None
    ) -> ListingVersion | None:
        stmt = select(MarketplaceListingVersionModel).where(
            MarketplaceListingVersionModel.listing_id == listing_id
        )
        if version_number is None:
            stmt = stmt.order_by(MarketplaceListingVersionModel.version_number.desc())
        else:
            stmt = stmt.where(MarketplaceListingVersionModel.version_number == version_number)
        result = await self._session.execute(stmt.limit(1))
        row = result.scalar_one_or_none()
        return None if row is None else _to_version(row)


def _to_review(row: MarketplaceReviewModel) -> Review:
    return Review(
        id=row.id,
        listing_id=row.listing_id,
        reviewer_workspace_id=row.reviewer_workspace_id,
        reviewer_name=row.reviewer_name,
        rating=row.rating,
        body=row.body,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlReviewRepository:
    """Implements `domain.ports.ReviewRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_listing(self, *, listing_id: str, limit: int) -> list[Review]:
        result = await self._session.execute(
            select(MarketplaceReviewModel)
            .where(MarketplaceReviewModel.listing_id == listing_id)
            .order_by(MarketplaceReviewModel.created_at.desc())
            .limit(limit)
        )
        return [_to_review(row) for row in result.scalars().all()]

    async def get_for_workspace(
        self, *, listing_id: str, reviewer_workspace_id: str
    ) -> Review | None:
        result = await self._session.execute(
            select(MarketplaceReviewModel).where(
                MarketplaceReviewModel.listing_id == listing_id,
                MarketplaceReviewModel.reviewer_workspace_id == reviewer_workspace_id,
            )
        )
        row = result.scalar_one_or_none()
        return None if row is None else _to_review(row)

    async def upsert(
        self,
        *,
        listing_id: str,
        reviewer_workspace_id: str,
        reviewer_name: str,
        rating: int,
        body: str,
    ) -> tuple[Review, int | None]:
        # Read the previous rating first: the caller needs it to move the
        # denormalized aggregate correctly, and an edit must shift the
        # sum without touching the count.
        existing = await self.get_for_workspace(
            listing_id=listing_id, reviewer_workspace_id=reviewer_workspace_id
        )
        previous = existing.rating if existing else None

        stmt = (
            pg_insert(MarketplaceReviewModel)
            .values(
                id=str(uuid.uuid4()),
                listing_id=listing_id,
                reviewer_workspace_id=reviewer_workspace_id,
                reviewer_name=reviewer_name,
                rating=rating,
                body=body,
            )
            .on_conflict_do_update(
                index_elements=[
                    MarketplaceReviewModel.listing_id,
                    MarketplaceReviewModel.reviewer_workspace_id,
                ],
                set_={
                    "rating": rating,
                    "body": body,
                    "reviewer_name": reviewer_name,
                    "updated_at": func.now(),
                },
            )
            .returning(MarketplaceReviewModel)
        )
        result = await self._session.execute(stmt)
        return _to_review(result.scalar_one()), previous

    async def delete(self, *, listing_id: str, reviewer_workspace_id: str) -> int | None:
        result = await self._session.execute(
            delete(MarketplaceReviewModel)
            .where(
                MarketplaceReviewModel.listing_id == listing_id,
                MarketplaceReviewModel.reviewer_workspace_id == reviewer_workspace_id,
            )
            .returning(MarketplaceReviewModel.rating)
        )
        return result.scalar_one_or_none()

    async def all_ratings(self, listing_id: str) -> list[int]:
        result = await self._session.execute(
            select(MarketplaceReviewModel.rating).where(
                MarketplaceReviewModel.listing_id == listing_id
            )
        )
        return [int(rating) for rating in result.scalars().all()]


class SqlCategoryRepository:
    """Implements `domain.ports.CategoryRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self) -> list[Category]:
        result = await self._session.execute(
            select(MarketplaceCategoryModel)
            .where(MarketplaceCategoryModel.is_active.is_(True))
            .order_by(MarketplaceCategoryModel.sort_order)
        )
        return [
            Category(
                slug=row.slug,
                name=row.name,
                description=row.description,
                sort_order=row.sort_order,
            )
            for row in result.scalars().all()
        ]

    async def exists(self, slug: str) -> bool:
        result = await self._session.execute(
            select(MarketplaceCategoryModel.slug).where(
                MarketplaceCategoryModel.slug == slug,
                MarketplaceCategoryModel.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none() is not None
