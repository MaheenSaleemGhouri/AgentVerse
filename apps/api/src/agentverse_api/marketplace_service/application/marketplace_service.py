"""Publishing to and browsing the marketplace.

Two things concentrate here rather than being spread across routes.

**Authorization for a public catalog.** Every read goes through
`domain.listing.may_view` and every write through `may_edit`, so the one
place the platform's default tenancy rule does not apply is applied
consistently. A route that forgot would leak someone's unpublished draft.

**The aggregate invariant.** A review write and the listing's
denormalized rating totals move together, in one transaction, computed
by the pure functions in `domain.review`. Nothing else in this context
writes those columns.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from agentverse_shared.embeddings.port import EmbeddingError, EmbeddingProvider

from agentverse_api.marketplace_service.application.hybrid_marketplace_search import hybrid_search
from agentverse_api.marketplace_service.domain.listing import (
    Listing,
    ListingKind,
    ListingNotPublishableError,
    ListingStatus,
    Pricing,
    assert_transition,
    may_edit,
    may_view,
    readiness_problems,
)
from agentverse_api.marketplace_service.domain.ports import (
    Category,
    CategoryRepository,
    ListingRepository,
    ListingSearchFilters,
    ListingSearchPort,
    ListingVersion,
    ListingVersionRepository,
    ReviewRepository,
)
from agentverse_api.marketplace_service.domain.review import (
    RatingAggregate,
    Review,
    SelfReviewError,
    apply_new_review,
    apply_removed_review,
    apply_updated_review,
    recompute_from,
    validate_rating,
)

logger = logging.getLogger(__name__)


class ListingNotFoundError(Exception):
    """Maps to HTTP 404.

    Also raised when a listing exists but the viewer may not see it — a
    404 rather than a 403, so an unpublished draft's existence is not
    discoverable by probing slugs.
    """

    def __init__(self, identifier: str) -> None:
        self.identifier = identifier
        super().__init__(f"No listing {identifier!r}")


class ListingForbiddenError(Exception):
    """The caller may see this listing but not change it. Maps to 403."""

    def __init__(self, listing_id: str) -> None:
        self.listing_id = listing_id
        super().__init__("Only the publishing workspace can edit this listing")


class SlugTakenError(Exception):
    """Maps to HTTP 409."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(f"The slug {slug!r} is already taken")


class UnknownCategoryError(Exception):
    """Maps to HTTP 422."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(f"No active category {slug!r}")


class WorkflowListingsNotYetSupportedError(Exception):
    """Maps to HTTP 422.

    The schema models workflow listings from the start so the
    marketplace does not need reshaping when the DAG workflow feature
    lands. Accepting one *today* would offer a publish button for
    something a customer cannot create — so it is refused with the
    reason, rather than silently absent.
    """

    def __init__(self) -> None:
        super().__init__(
            "Workflow listings are not available yet — the workflow builder has not "
            "shipped, so there is nothing to publish. Agent listings are available now."
        )


_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """A URL-safe slug from a title.

    Not guaranteed unique — the caller checks and disambiguates, because
    uniqueness is a property of the catalog rather than of the string.
    """
    slug = _SLUG_PATTERN.sub("-", title.lower()).strip("-")
    return slug[:64] or "listing"


@dataclass(slots=True)
class MarketplaceService:
    listings: ListingRepository
    versions: ListingVersionRepository
    reviews: ReviewRepository
    categories: CategoryRepository
    #: Hybrid search's two collaborators. Both optional and both trail
    #: the required fields precisely so every existing call site (tests
    #: included) that only cares about publishing/browsing keeps working
    #: unchanged — hybrid ranking activates only when both are wired,
    #: and `browse` falls back to its original keyword-only path
    #: otherwise (see `browse` and `_maybe_embed` below).
    search: ListingSearchPort | None = None
    embedder: EmbeddingProvider | None = None

    # ---- catalog (public) --------------------------------------------

    async def browse(
        self,
        *,
        category_slug: str | None = None,
        kind: ListingKind | None = None,
        query: str | None = None,
        featured_only: bool = False,
        free_only: bool = False,
        official_only: bool | None = None,
        sort: str = "popular",
        limit: int = 24,
        offset: int = 0,
    ) -> tuple[list[Listing], int]:
        """The public catalog. No workspace filter, deliberately.

        `official_only` is tri-state: `True` is the first-party template
        library, `False` is community listings only, `None` is the whole
        catalog. A bool could not express "everything", which is what a
        catalog page wants by default.

        A non-empty `query` runs through hybrid (semantic + keyword)
        search when this service was wired with a `search` port and an
        `embedder` (`get_marketplace_service`); otherwise — and for any
        request with no `query` at all — this is the original
        keyword-only/no-query path, byte-for-byte. `sort` is ignored on
        the hybrid path: once someone has typed a search, relevance is
        the sort they asked for, and re-sorting the results of a search
        by popularity would bury the best match beneath the most
        installed one.
        """
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)
        if query and self.search is not None and self.embedder is not None:
            return await self._hybrid_browse(
                query=query,
                filters=ListingSearchFilters(
                    category_slug=category_slug,
                    kind=kind,
                    featured_only=featured_only,
                    free_only=free_only,
                    official_only=official_only,
                ),
                limit=limit,
                offset=offset,
            )
        return await self.listings.browse(
            category_slug=category_slug,
            kind=kind,
            query=query,
            featured_only=featured_only,
            free_only=free_only,
            official_only=official_only,
            sort=sort,
            limit=limit,
            offset=offset,
        )

    async def _hybrid_browse(
        self, *, query: str, filters: ListingSearchFilters, limit: int, offset: int
    ) -> tuple[list[Listing], int]:
        # Narrows for mypy — the caller (`browse`) already checked both.
        assert self.search is not None
        assert self.embedder is not None
        fused = await hybrid_search(
            query=query, filters=filters, search=self.search, embedder=self.embedder
        )
        page = fused[offset : offset + limit]
        by_slug = {listing.slug: listing for listing in await self.listings.get_by_slugs(
            [match.id for match in page]
        )}
        ordered = [by_slug[match.id] for match in page if match.id in by_slug]
        # The count of ranked candidates actually available, not a true
        # `COUNT(*)` of every matching row in the catalog — an inherent
        # property of a ranked, capped fusion rather than a filtered SQL
        # WHERE, and standard for ranked search UX (a result count past
        # the first page of a search is rarely exact anywhere).
        return ordered, len(fused)

    async def list_categories(self) -> list[Category]:
        return await self.categories.list_active()

    async def get(self, *, slug: str, viewer_workspace_id: str | None) -> Listing:
        """One listing, or 404.

        A listing the viewer may not see raises the *same* error as one
        that does not exist. Distinguishing them would let anyone
        enumerate unpublished drafts by watching which slugs answer 403.
        """
        listing = await self.listings.get_by_slug(slug)
        if listing is None or not may_view(
            listing=listing, viewer_workspace_id=viewer_workspace_id
        ):
            raise ListingNotFoundError(slug)
        return listing

    async def versions_of(
        self, *, slug: str, viewer_workspace_id: str | None
    ) -> list[ListingVersion]:
        listing = await self.get(slug=slug, viewer_workspace_id=viewer_workspace_id)
        return await self.versions.list_versions(listing.id)

    # ---- publishing --------------------------------------------------

    async def create_listing(
        self,
        *,
        publisher_workspace_id: str,
        publisher_name: str,
        kind: ListingKind,
        title: str,
        summary: str,
        description: str,
        category_slug: str,
        pricing: Pricing,
        price_cents: int,
        slug: str | None = None,
    ) -> Listing:
        """Create a draft. Nothing is public until it is submitted and
        approved.
        """
        if kind is ListingKind.WORKFLOW:
            raise WorkflowListingsNotYetSupportedError
        if not await self.categories.exists(category_slug):
            raise UnknownCategoryError(category_slug)

        candidate = slug or slugify(title)
        if await self.listings.slug_exists(candidate):
            if slug is not None:
                # An explicitly requested slug that is taken is a
                # conflict the caller must resolve — silently changing it
                # would give them a URL they did not ask for.
                raise SlugTakenError(candidate)
            candidate = await self._disambiguate(candidate)

        return await self.listings.create(
            slug=candidate,
            kind=kind,
            publisher_workspace_id=publisher_workspace_id,
            publisher_name=publisher_name,
            title=title,
            summary=summary,
            description=description,
            category_slug=category_slug,
            pricing=pricing,
            price_cents=price_cents,
        )

    async def _disambiguate(self, base: str) -> str:
        """Append a counter until the slug is free.

        Bounded rather than unbounded: after a handful of collisions the
        title is genuinely ambiguous and a random suffix is better than
        `agent-247`.
        """
        for suffix in range(2, 12):
            candidate = f"{base}-{suffix}"
            if not await self.listings.slug_exists(candidate):
                return candidate
        import uuid

        return f"{base}-{uuid.uuid4().hex[:6]}"

    async def update_listing(
        self,
        *,
        slug: str,
        actor_workspace_id: str,
        title: str | None = None,
        summary: str | None = None,
        description: str | None = None,
        category_slug: str | None = None,
        pricing: Pricing | None = None,
        price_cents: int | None = None,
    ) -> Listing:
        listing = await self._owned(slug=slug, actor_workspace_id=actor_workspace_id)
        if category_slug is not None and not await self.categories.exists(category_slug):
            raise UnknownCategoryError(category_slug)
        return await self.listings.update_details(
            listing_id=listing.id,
            title=title,
            summary=summary,
            description=description,
            category_slug=category_slug,
            pricing=pricing,
            price_cents=price_cents,
        )

    async def publish_version(
        self,
        *,
        slug: str,
        actor_workspace_id: str,
        config: dict[str, object],
        changelog: str,
        source_agent_version_id: str | None = None,
    ) -> ListingVersion:
        """Snapshot the current configuration as a new version.

        The config is copied, not referenced. The publisher can delete
        their source agent afterwards and every install made from this
        version keeps working — which is the only way a marketplace can
        be trusted.
        """
        listing = await self._owned(slug=slug, actor_workspace_id=actor_workspace_id)
        return await self.versions.publish_version(
            listing_id=listing.id,
            version_number=listing.latest_version + 1,
            config=config,
            changelog=changelog,
            source_agent_version_id=source_agent_version_id,
        )

    async def submit_for_review(self, *, slug: str, actor_workspace_id: str) -> Listing:
        """Move a draft into the moderation queue.

        Readiness is checked here rather than at draft creation, so a
        publisher can save work in progress without fighting validation —
        and every problem is reported at once rather than one per round
        trip.
        """
        listing = await self._owned(slug=slug, actor_workspace_id=actor_workspace_id)
        has_version = (
            await self.versions.get_version(listing_id=listing.id, version_number=None)
        ) is not None
        problems = readiness_problems(listing=listing, has_version=has_version)
        if problems:
            raise ListingNotPublishableError(problems)
        assert_transition(current=listing.status, target=ListingStatus.PENDING_REVIEW)
        return await self.listings.set_status(
            listing_id=listing.id, status=ListingStatus.PENDING_REVIEW
        )

    async def unlist(self, *, slug: str, actor_workspace_id: str) -> Listing:
        """Withdraw from the catalog without breaking existing installs.

        Not deletion: installs made from this listing are copies living
        in other workspaces, and the row and its snapshots survive so
        their provenance stays explicable.
        """
        listing = await self._owned(slug=slug, actor_workspace_id=actor_workspace_id)
        assert_transition(current=listing.status, target=ListingStatus.UNLISTED)
        return await self.listings.set_status(listing_id=listing.id, status=ListingStatus.UNLISTED)

    async def relist(self, *, slug: str, actor_workspace_id: str) -> Listing:
        listing = await self._owned(slug=slug, actor_workspace_id=actor_workspace_id)
        assert_transition(current=listing.status, target=ListingStatus.PUBLISHED)
        republished = await self.listings.set_status(
            listing_id=listing.id, status=ListingStatus.PUBLISHED
        )
        await self._maybe_embed(republished)
        return republished

    async def list_mine(self, *, publisher_workspace_id: str, limit: int = 50) -> list[Listing]:
        return await self.listings.list_for_publisher(
            publisher_workspace_id=publisher_workspace_id, limit=limit
        )

    # ---- moderation (platform admin) ---------------------------------

    async def approve(self, *, listing_id: str) -> Listing:
        """Platform-admin action, not a publisher one.

        Deliberately keyed by id rather than slug and taking no actor
        workspace: this authority is checked at the route by the
        admin dependency, and routing it through `may_edit` would let a
        publisher approve themselves.
        """
        listing = await self._require(listing_id)
        assert_transition(current=listing.status, target=ListingStatus.PUBLISHED)
        published = await self.listings.set_status(
            listing_id=listing.id, status=ListingStatus.PUBLISHED
        )
        await self._maybe_embed(published)
        return published

    async def reject(self, *, listing_id: str, note: str) -> Listing:
        """A rejection carries its reason. A publisher told "rejected"
        with no note cannot fix anything.
        """
        listing = await self._require(listing_id)
        assert_transition(current=listing.status, target=ListingStatus.REJECTED)
        return await self.listings.set_status(
            listing_id=listing.id, status=ListingStatus.REJECTED, moderation_note=note
        )

    async def set_featured(self, *, listing_id: str, is_featured: bool) -> Listing:
        await self._require(listing_id)
        return await self.listings.set_featured(listing_id=listing_id, is_featured=is_featured)

    # ---- reviews -----------------------------------------------------

    async def list_reviews(
        self, *, slug: str, viewer_workspace_id: str | None, limit: int = 50
    ) -> list[Review]:
        listing = await self.get(slug=slug, viewer_workspace_id=viewer_workspace_id)
        return await self.reviews.list_for_listing(
            listing_id=listing.id, limit=min(max(limit, 1), 200)
        )

    async def submit_review(
        self,
        *,
        slug: str,
        reviewer_workspace_id: str,
        reviewer_name: str,
        rating: int,
        body: str,
    ) -> Review:
        """Write a review and move the listing's aggregate with it.

        Both happen in one transaction. The aggregate is denormalized
        precisely so the catalog does not average a listing's whole
        review history on every render, and the only thing that keeps
        the two honest is that nothing writes one without the other.
        """
        validate_rating(rating)
        listing = await self.get(slug=slug, viewer_workspace_id=reviewer_workspace_id)
        if listing.publisher_workspace_id == reviewer_workspace_id:
            # Refused at write time rather than filtered at read time: a
            # hidden self-review still has to be excluded from the
            # aggregate by every consumer, and one of them will forget.
            raise SelfReviewError(listing.id)

        review, previous = await self.reviews.upsert(
            listing_id=listing.id,
            reviewer_workspace_id=reviewer_workspace_id,
            reviewer_name=reviewer_name,
            rating=rating,
            body=body,
        )
        current = RatingAggregate(rating_sum=listing.rating_sum, rating_count=listing.rating_count)
        updated = (
            apply_updated_review(current=current, previous_rating=previous, new_rating=rating)
            if previous is not None
            else apply_new_review(current=current, rating=rating)
        )
        await self.listings.set_rating_aggregate(listing_id=listing.id, aggregate=updated)
        return review

    async def withdraw_review(self, *, slug: str, reviewer_workspace_id: str) -> bool:
        listing = await self.get(slug=slug, viewer_workspace_id=reviewer_workspace_id)
        removed = await self.reviews.delete(
            listing_id=listing.id, reviewer_workspace_id=reviewer_workspace_id
        )
        if removed is None:
            return False
        updated = apply_removed_review(
            current=RatingAggregate(
                rating_sum=listing.rating_sum, rating_count=listing.rating_count
            ),
            rating=removed,
        )
        await self.listings.set_rating_aggregate(listing_id=listing.id, aggregate=updated)
        return True

    async def reconcile_ratings(self, listing_id: str) -> RatingAggregate | None:
        """Re-derive the aggregate from the reviews.

        `None` when it already agrees. A disagreement means something
        wrote the denormalized columns outside the transaction that owns
        them — worth a human looking at, which is why this reports
        rather than repairs.
        """
        listing = await self._require(listing_id)
        fresh = recompute_from(await self.reviews.all_ratings(listing_id))
        if fresh.rating_sum == listing.rating_sum and fresh.rating_count == listing.rating_count:
            return None
        return fresh

    # ---- helpers -----------------------------------------------------

    async def _maybe_embed(self, listing: Listing) -> None:
        """Best-effort: embeds a just-(re)published listing for hybrid
        search. No-ops if this service was not wired with an embedder
        (`browse` then simply never takes the hybrid path either).

        Failures here are logged, never raised. Publishing/relisting is
        the moderation-authority action of record; a transient
        embedding-provider outage must not block it, and would otherwise
        turn a search-quality concern into a publishing incident.
        """
        if self.embedder is None:
            return
        try:
            embedded = await self.embedder.embed(
                [f"{listing.title}\n\n{listing.summary}\n\n{listing.description}"]
            )
        except EmbeddingError:
            logger.warning("marketplace listing embedding failed", extra={"listing_id": listing.id})
            return
        await self.listings.set_embedding(
            listing_id=listing.id,
            embedding=embedded.vectors[0],
            embedding_model=embedded.model,
            embedding_model_version=embedded.model_version,
        )

    async def _require(self, listing_id: str) -> Listing:
        listing = await self.listings.get_by_id(listing_id)
        if listing is None:
            raise ListingNotFoundError(listing_id)
        return listing

    async def _owned(self, *, slug: str, actor_workspace_id: str) -> Listing:
        listing = await self.listings.get_by_slug(slug)
        if listing is None or not may_view(listing=listing, viewer_workspace_id=actor_workspace_id):
            raise ListingNotFoundError(slug)
        if not may_edit(listing=listing, actor_workspace_id=actor_workspace_id):
            # 403 here rather than 404: the listing is published and
            # therefore already public, so its existence is not a secret
            # — only the right to change it is.
            raise ListingForbiddenError(listing.id)
        return listing
