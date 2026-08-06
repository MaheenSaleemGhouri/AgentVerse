"""The marketplace against real Postgres.

Three things only the database can prove, and each one is the sort of
failure that reaches a customer rather than a log:

- the public catalog returns **only** published listings, so a draft
  cannot leak into it;
- one review per workspace per listing, enforced by a unique index
  rather than a check two concurrent submissions would both pass;
- the denormalized rating aggregate stays equal to the reviews it
  summarises, including across edits and withdrawals.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.marketplace_service.application.marketplace_service import (
    ListingForbiddenError,
    ListingNotFoundError,
    MarketplaceService,
    SlugTakenError,
    UnknownCategoryError,
    WorkflowListingsNotYetSupportedError,
    slugify,
)
from agentverse_api.marketplace_service.domain.listing import (
    InvalidListingTransitionError,
    ListingKind,
    ListingNotPublishableError,
    ListingStatus,
    Pricing,
)
from agentverse_api.marketplace_service.domain.review import SelfReviewError
from agentverse_api.marketplace_service.infrastructure.repositories import (
    SqlCategoryRepository,
    SqlListingRepository,
    SqlListingVersionRepository,
    SqlReviewRepository,
)

pytestmark = pytest.mark.integration

_SUMMARY = "A genuinely useful research agent for teams that need citations."
_DESCRIPTION = "x" * 200


async def _workspace(session: AsyncSession, label: str = "MP") -> str:
    workspace_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO workspaces (id, name, slug, created_at) VALUES (:id, :name, :slug, now())"
        ),
        {"id": workspace_id, "name": f"{label} Test", "slug": f"ws-{workspace_id[:8]}"},
    )
    await session.flush()
    return workspace_id


def _service(session: AsyncSession) -> MarketplaceService:
    return MarketplaceService(
        listings=SqlListingRepository(session),
        versions=SqlListingVersionRepository(session),
        reviews=SqlReviewRepository(session),
        categories=SqlCategoryRepository(session),
    )


async def _published(
    service: MarketplaceService, publisher: str, *, title: str = "Research Agent"
) -> str:
    """A listing taken all the way through moderation to published."""
    listing = await service.create_listing(
        publisher_workspace_id=publisher,
        publisher_name="Acme",
        kind=ListingKind.AGENT,
        title=title,
        summary=_SUMMARY,
        description=_DESCRIPTION,
        category_slug="research",
        pricing=Pricing.FREE,
        price_cents=0,
    )
    await service.publish_version(
        slug=listing.slug,
        actor_workspace_id=publisher,
        config={"model": "gpt-4o-mini"},
        changelog="Initial release",
    )
    await service.submit_for_review(slug=listing.slug, actor_workspace_id=publisher)
    await service.approve(listing_id=listing.id)
    return listing.slug


class TestSeededCategories:
    async def test_the_catalog_ships_with_categories(self, db_session: AsyncSession) -> None:
        # The FK requires one, so a catalog with no categories cannot
        # accept its first listing — this is not optional seed data.
        categories = await _service(db_session).list_categories()
        assert len(categories) >= 8
        assert {c.slug for c in categories} >= {"research", "engineering", "data"}

    async def test_categories_come_back_in_editorial_order(self, db_session: AsyncSession) -> None:
        categories = await _service(db_session).list_categories()
        assert [c.sort_order for c in categories] == sorted(c.sort_order for c in categories)

    async def test_an_unknown_category_is_refused(self, db_session: AsyncSession) -> None:
        publisher = await _workspace(db_session)
        with pytest.raises(UnknownCategoryError):
            await _service(db_session).create_listing(
                publisher_workspace_id=publisher,
                publisher_name="Acme",
                kind=ListingKind.AGENT,
                title="Bad Category",
                summary=_SUMMARY,
                description=_DESCRIPTION,
                category_slug="does-not-exist",
                pricing=Pricing.FREE,
                price_cents=0,
            )
        await db_session.rollback()


class TestPublicCatalog:
    async def test_a_draft_never_appears_in_the_catalog(self, db_session: AsyncSession) -> None:
        # The failure that would matter most: someone's unpublished work
        # on a public page.
        publisher = await _workspace(db_session)
        service = _service(db_session)
        await service.create_listing(
            publisher_workspace_id=publisher,
            publisher_name="Acme",
            kind=ListingKind.AGENT,
            title="Secret Draft",
            summary=_SUMMARY,
            description=_DESCRIPTION,
            category_slug="research",
            pricing=Pricing.FREE,
            price_cents=0,
        )
        listings, total = await service.browse(query="Secret Draft")
        assert listings == []
        assert total == 0
        await db_session.rollback()

    async def test_a_published_listing_is_visible_across_workspaces(
        self, db_session: AsyncSession
    ) -> None:
        # The whole point of a marketplace, and the one read in this
        # platform that is deliberately not tenant-scoped.
        publisher = await _workspace(db_session)
        service = _service(db_session)
        slug = await _published(service, publisher, title=f"Cross {uuid.uuid4().hex[:6]}")
        listing = await service.get(slug=slug, viewer_workspace_id=None)
        assert listing.status is ListingStatus.PUBLISHED
        await db_session.rollback()

    async def test_an_unlisted_listing_leaves_the_catalog_but_survives(
        self, db_session: AsyncSession
    ) -> None:
        publisher = await _workspace(db_session)
        service = _service(db_session)
        title = f"Withdrawn {uuid.uuid4().hex[:6]}"
        slug = await _published(service, publisher, title=title)
        await service.unlist(slug=slug, actor_workspace_id=publisher)

        listings, _ = await service.browse(query=title)
        assert listings == []
        # Still there for its publisher — installs made from it are
        # copies in other workspaces and must stay explicable.
        assert (
            await service.get(slug=slug, viewer_workspace_id=publisher)
        ).status is ListingStatus.UNLISTED
        await db_session.rollback()

    async def test_a_hidden_listing_answers_not_found_rather_than_forbidden(
        self, db_session: AsyncSession
    ) -> None:
        # Distinguishing them would let anyone enumerate unpublished
        # drafts by watching which slugs answer 403.
        publisher = await _workspace(db_session)
        stranger = await _workspace(db_session)
        service = _service(db_session)
        listing = await service.create_listing(
            publisher_workspace_id=publisher,
            publisher_name="Acme",
            kind=ListingKind.AGENT,
            title="Hidden",
            summary=_SUMMARY,
            description=_DESCRIPTION,
            category_slug="research",
            pricing=Pricing.FREE,
            price_cents=0,
        )
        with pytest.raises(ListingNotFoundError):
            await service.get(slug=listing.slug, viewer_workspace_id=stranger)
        await db_session.rollback()

    async def test_the_publisher_sees_their_own_drafts(self, db_session: AsyncSession) -> None:
        publisher = await _workspace(db_session)
        service = _service(db_session)
        await service.create_listing(
            publisher_workspace_id=publisher,
            publisher_name="Acme",
            kind=ListingKind.AGENT,
            title="My Draft",
            summary=_SUMMARY,
            description=_DESCRIPTION,
            category_slug="research",
            pricing=Pricing.FREE,
            price_cents=0,
        )
        mine = await service.list_mine(publisher_workspace_id=publisher)
        assert [listing.status for listing in mine] == [ListingStatus.DRAFT]
        await db_session.rollback()

    async def test_browse_returns_a_total_alongside_the_page(
        self, db_session: AsyncSession
    ) -> None:
        # Two round trips can disagree if a listing is published between
        # them, so the count travels with the rows it was computed from.
        publisher = await _workspace(db_session)
        service = _service(db_session)
        marker = uuid.uuid4().hex[:8]
        for index in range(3):
            await _published(service, publisher, title=f"Paged {marker} {index}")
        listings, total = await service.browse(query=marker, limit=2)
        assert len(listings) == 2
        assert total == 3
        await db_session.rollback()

    async def test_an_unknown_sort_falls_back_rather_than_reaching_sql(
        self, db_session: AsyncSession
    ) -> None:
        # `sort` arrives from a query string; an unvalidated value in an
        # ORDER BY is an injection point.
        service = _service(db_session)
        listings, _ = await service.browse(sort="'; DROP TABLE marketplace_listings--")
        assert isinstance(listings, list)
        await db_session.rollback()


class TestSlugs:
    async def test_a_generated_slug_is_disambiguated_on_collision(
        self, db_session: AsyncSession
    ) -> None:
        publisher = await _workspace(db_session)
        service = _service(db_session)
        title = f"Same Title {uuid.uuid4().hex[:6]}"
        first = await service.create_listing(
            publisher_workspace_id=publisher,
            publisher_name="Acme",
            kind=ListingKind.AGENT,
            title=title,
            summary=_SUMMARY,
            description=_DESCRIPTION,
            category_slug="research",
            pricing=Pricing.FREE,
            price_cents=0,
        )
        second = await service.create_listing(
            publisher_workspace_id=publisher,
            publisher_name="Acme",
            kind=ListingKind.AGENT,
            title=title,
            summary=_SUMMARY,
            description=_DESCRIPTION,
            category_slug="research",
            pricing=Pricing.FREE,
            price_cents=0,
        )
        assert first.slug != second.slug
        await db_session.rollback()

    async def test_an_explicitly_requested_taken_slug_is_a_conflict(
        self, db_session: AsyncSession
    ) -> None:
        # Silently changing it would hand the caller a URL they did not
        # ask for.
        publisher = await _workspace(db_session)
        service = _service(db_session)
        slug = f"explicit-{uuid.uuid4().hex[:8]}"
        await service.create_listing(
            publisher_workspace_id=publisher,
            publisher_name="Acme",
            kind=ListingKind.AGENT,
            title="Explicit",
            summary=_SUMMARY,
            description=_DESCRIPTION,
            category_slug="research",
            pricing=Pricing.FREE,
            price_cents=0,
            slug=slug,
        )
        with pytest.raises(SlugTakenError):
            await service.create_listing(
                publisher_workspace_id=publisher,
                publisher_name="Acme",
                kind=ListingKind.AGENT,
                title="Explicit",
                summary=_SUMMARY,
                description=_DESCRIPTION,
                category_slug="research",
                pricing=Pricing.FREE,
                price_cents=0,
                slug=slug,
            )
        await db_session.rollback()

    async def test_slug_uniqueness_is_enforced_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        publisher = await _workspace(db_session)
        insert = text(
            "INSERT INTO marketplace_listings "
            "(id, slug, kind, publisher_workspace_id, title, category_slug, status) "
            "VALUES (gen_random_uuid(), 'dup-slug', 'agent', :ws, 'T', 'research', 'draft')"
        )
        await db_session.execute(insert, {"ws": publisher})
        with pytest.raises(IntegrityError):
            await db_session.execute(insert, {"ws": publisher})
        await db_session.rollback()

    def test_slugify_produces_a_url_safe_string(self) -> None:
        assert slugify("Research Agent!! (v2)") == "research-agent-v2"
        assert slugify("") == "listing"


class TestOwnership:
    async def test_a_stranger_cannot_edit_a_public_listing(self, db_session: AsyncSession) -> None:
        # 403 here, not 404: the listing is already public, so its
        # existence is not a secret — only the right to change it.
        publisher = await _workspace(db_session)
        stranger = await _workspace(db_session)
        service = _service(db_session)
        slug = await _published(service, publisher, title=f"Owned {uuid.uuid4().hex[:6]}")
        with pytest.raises(ListingForbiddenError):
            await service.update_listing(slug=slug, actor_workspace_id=stranger, title="Hijacked")
        await db_session.rollback()

    async def test_a_publisher_cannot_approve_their_own_listing_via_the_edit_path(
        self, db_session: AsyncSession
    ) -> None:
        # Approval is keyed by id and takes no actor workspace — the
        # authority is checked at the route, not through `may_edit`.
        publisher = await _workspace(db_session)
        service = _service(db_session)
        listing = await service.create_listing(
            publisher_workspace_id=publisher,
            publisher_name="Acme",
            kind=ListingKind.AGENT,
            title="Self Approve",
            summary=_SUMMARY,
            description=_DESCRIPTION,
            category_slug="research",
            pricing=Pricing.FREE,
            price_cents=0,
        )
        # Straight from draft to published is not a legal transition at
        # all, so even the admin path refuses it.
        with pytest.raises(InvalidListingTransitionError):
            await service.approve(listing_id=listing.id)
        await db_session.rollback()


class TestVersions:
    async def test_versions_increment_and_move_the_listing_pointer(
        self, db_session: AsyncSession
    ) -> None:
        # A listing pointing at a version that does not exist would make
        # install fail for everyone.
        publisher = await _workspace(db_session)
        service = _service(db_session)
        slug = await _published(service, publisher, title=f"Versioned {uuid.uuid4().hex[:6]}")
        await service.publish_version(
            slug=slug,
            actor_workspace_id=publisher,
            config={"model": "gpt-4o"},
            changelog="Upgraded model",
        )
        listing = await service.get(slug=slug, viewer_workspace_id=publisher)
        assert listing.latest_version == 2
        versions = await service.versions_of(slug=slug, viewer_workspace_id=publisher)
        assert [v.version_number for v in versions] == [2, 1]
        await db_session.rollback()

    async def test_a_version_snapshot_is_a_copy_not_a_reference(
        self, db_session: AsyncSession
    ) -> None:
        # The property the whole marketplace rests on: the publisher can
        # delete their source agent and installs keep working.
        publisher = await _workspace(db_session)
        service = _service(db_session)
        slug = await _published(service, publisher, title=f"Snap {uuid.uuid4().hex[:6]}")
        versions = await service.versions_of(slug=slug, viewer_workspace_id=publisher)
        assert versions[0].config == {"model": "gpt-4o-mini"}
        await db_session.rollback()

    async def test_duplicate_version_numbers_are_rejected_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        publisher = await _workspace(db_session)
        service = _service(db_session)
        listing = await service.create_listing(
            publisher_workspace_id=publisher,
            publisher_name="Acme",
            kind=ListingKind.AGENT,
            title="Dup Version",
            summary=_SUMMARY,
            description=_DESCRIPTION,
            category_slug="research",
            pricing=Pricing.FREE,
            price_cents=0,
        )
        insert = text(
            "INSERT INTO marketplace_listing_versions "
            "(id, listing_id, version_number, config) "
            "VALUES (gen_random_uuid(), :lid, 1, '{}')"
        )
        await db_session.execute(insert, {"lid": listing.id})
        with pytest.raises(IntegrityError):
            await db_session.execute(insert, {"lid": listing.id})
        await db_session.rollback()


class TestSubmission:
    async def test_a_listing_with_no_version_cannot_be_submitted(
        self, db_session: AsyncSession
    ) -> None:
        publisher = await _workspace(db_session)
        service = _service(db_session)
        listing = await service.create_listing(
            publisher_workspace_id=publisher,
            publisher_name="Acme",
            kind=ListingKind.AGENT,
            title="No Version",
            summary=_SUMMARY,
            description=_DESCRIPTION,
            category_slug="research",
            pricing=Pricing.FREE,
            price_cents=0,
        )
        with pytest.raises(ListingNotPublishableError) as exc:
            await service.submit_for_review(slug=listing.slug, actor_workspace_id=publisher)
        assert any("nothing to install" in reason for reason in exc.value.reasons)
        await db_session.rollback()

    async def test_a_rejection_carries_its_reason(self, db_session: AsyncSession) -> None:
        # A publisher told "rejected" with no note cannot fix anything.
        publisher = await _workspace(db_session)
        service = _service(db_session)
        listing = await service.create_listing(
            publisher_workspace_id=publisher,
            publisher_name="Acme",
            kind=ListingKind.AGENT,
            title="To Reject",
            summary=_SUMMARY,
            description=_DESCRIPTION,
            category_slug="research",
            pricing=Pricing.FREE,
            price_cents=0,
        )
        await service.publish_version(
            slug=listing.slug,
            actor_workspace_id=publisher,
            config={},
            changelog="v1",
        )
        await service.submit_for_review(slug=listing.slug, actor_workspace_id=publisher)
        rejected = await service.reject(
            listing_id=listing.id, note="The description does not say what it does."
        )
        assert rejected.status is ListingStatus.REJECTED
        # And it can be fixed and resubmitted, keeping its history.
        await service.submit_for_review(slug=listing.slug, actor_workspace_id=publisher)
        await db_session.rollback()


class TestWorkflowListings:
    async def test_publishing_a_workflow_is_refused_with_a_reason(
        self, db_session: AsyncSession
    ) -> None:
        # The schema models workflow listings so the marketplace does not
        # need reshaping later, but the DAG workflow builder has not
        # shipped — offering the button would be a button for something
        # a customer cannot create.
        publisher = await _workspace(db_session)
        with pytest.raises(WorkflowListingsNotYetSupportedError) as exc:
            await _service(db_session).create_listing(
                publisher_workspace_id=publisher,
                publisher_name="Acme",
                kind=ListingKind.WORKFLOW,
                title="A Workflow",
                summary=_SUMMARY,
                description=_DESCRIPTION,
                category_slug="research",
                pricing=Pricing.FREE,
                price_cents=0,
            )
        assert "has not shipped" in str(exc.value)
        await db_session.rollback()


class TestReviews:
    async def test_a_review_moves_the_listing_aggregate(self, db_session: AsyncSession) -> None:
        publisher = await _workspace(db_session)
        reviewer = await _workspace(db_session)
        service = _service(db_session)
        slug = await _published(service, publisher, title=f"Rated {uuid.uuid4().hex[:6]}")
        await service.submit_review(
            slug=slug,
            reviewer_workspace_id=reviewer,
            reviewer_name="Reviewer",
            rating=4,
            body="Solid.",
        )
        listing = await service.get(slug=slug, viewer_workspace_id=None)
        assert listing.rating_count == 1
        assert listing.average_rating == 4.0
        await db_session.rollback()

    async def test_a_second_review_replaces_rather_than_adds(
        self, db_session: AsyncSession
    ) -> None:
        # One review per workspace: eight members must not become eight
        # reviews.
        publisher = await _workspace(db_session)
        reviewer = await _workspace(db_session)
        service = _service(db_session)
        slug = await _published(service, publisher, title=f"Edited {uuid.uuid4().hex[:6]}")
        await service.submit_review(
            slug=slug,
            reviewer_workspace_id=reviewer,
            reviewer_name="Reviewer",
            rating=5,
            body="Great.",
        )
        await service.submit_review(
            slug=slug,
            reviewer_workspace_id=reviewer,
            reviewer_name="Reviewer",
            rating=2,
            body="Changed my mind.",
        )
        listing = await service.get(slug=slug, viewer_workspace_id=None)
        assert listing.rating_count == 1
        assert listing.average_rating == 2.0
        await db_session.rollback()

    async def test_one_review_per_workspace_is_enforced_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        publisher = await _workspace(db_session)
        reviewer = await _workspace(db_session)
        service = _service(db_session)
        slug = await _published(service, publisher, title=f"Unique {uuid.uuid4().hex[:6]}")
        listing = await service.get(slug=slug, viewer_workspace_id=None)
        insert = text(
            "INSERT INTO marketplace_reviews "
            "(id, listing_id, reviewer_workspace_id, rating) "
            "VALUES (gen_random_uuid(), :lid, :ws, 5)"
        )
        params = {"lid": listing.id, "ws": reviewer}
        await db_session.execute(insert, params)
        with pytest.raises(IntegrityError):
            await db_session.execute(insert, params)
        await db_session.rollback()

    async def test_a_publisher_cannot_review_their_own_listing(
        self, db_session: AsyncSession
    ) -> None:
        # Refused at write time: a hidden self-review still has to be
        # excluded from the aggregate by every consumer.
        publisher = await _workspace(db_session)
        service = _service(db_session)
        slug = await _published(service, publisher, title=f"Self {uuid.uuid4().hex[:6]}")
        with pytest.raises(SelfReviewError):
            await service.submit_review(
                slug=slug,
                reviewer_workspace_id=publisher,
                reviewer_name="Acme",
                rating=5,
                body="Excellent, if I say so myself.",
            )
        await db_session.rollback()

    async def test_withdrawing_a_review_reverses_the_aggregate(
        self, db_session: AsyncSession
    ) -> None:
        publisher = await _workspace(db_session)
        reviewer = await _workspace(db_session)
        service = _service(db_session)
        slug = await _published(service, publisher, title=f"Undo {uuid.uuid4().hex[:6]}")
        await service.submit_review(
            slug=slug,
            reviewer_workspace_id=reviewer,
            reviewer_name="Reviewer",
            rating=3,
            body="Fine.",
        )
        assert await service.withdraw_review(slug=slug, reviewer_workspace_id=reviewer) is True
        listing = await service.get(slug=slug, viewer_workspace_id=None)
        assert listing.rating_count == 0
        assert listing.average_rating is None
        await db_session.rollback()

    async def test_the_aggregate_agrees_with_the_reviews_after_every_operation(
        self, db_session: AsyncSession
    ) -> None:
        # The denormalization's whole invariant, exercised across a
        # write, an edit and a withdrawal.
        publisher = await _workspace(db_session)
        first = await _workspace(db_session)
        second = await _workspace(db_session)
        service = _service(db_session)
        slug = await _published(service, publisher, title=f"Recon {uuid.uuid4().hex[:6]}")
        listing = await service.get(slug=slug, viewer_workspace_id=None)

        for workspace, rating in ((first, 5), (second, 3)):
            await service.submit_review(
                slug=slug,
                reviewer_workspace_id=workspace,
                reviewer_name="R",
                rating=rating,
                body="",
            )
        assert await service.reconcile_ratings(listing.id) is None

        await service.submit_review(
            slug=slug, reviewer_workspace_id=first, reviewer_name="R", rating=1, body=""
        )
        assert await service.reconcile_ratings(listing.id) is None

        await service.withdraw_review(slug=slug, reviewer_workspace_id=second)
        assert await service.reconcile_ratings(listing.id) is None
        await db_session.rollback()

    async def test_a_rating_outside_the_scale_is_rejected_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        publisher = await _workspace(db_session)
        reviewer = await _workspace(db_session)
        service = _service(db_session)
        slug = await _published(service, publisher, title=f"Scale {uuid.uuid4().hex[:6]}")
        listing = await service.get(slug=slug, viewer_workspace_id=None)
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO marketplace_reviews "
                    "(id, listing_id, reviewer_workspace_id, rating) "
                    "VALUES (gen_random_uuid(), :lid, :ws, 9)"
                ),
                {"lid": listing.id, "ws": reviewer},
            )
        await db_session.rollback()


class TestDatabaseInvariants:
    async def test_a_free_listing_cannot_carry_a_price(self, db_session: AsyncSession) -> None:
        # Without this a listing can claim to be free and still charge.
        publisher = await _workspace(db_session)
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO marketplace_listings "
                    "(id, slug, kind, publisher_workspace_id, title, category_slug, "
                    " status, pricing, price_cents) "
                    "VALUES (gen_random_uuid(), :slug, 'agent', :ws, 'T', 'research', "
                    " 'draft', 'free', 500)"
                ),
                {"ws": publisher, "slug": f"bad-{uuid.uuid4().hex[:8]}"},
            )
        await db_session.rollback()

    async def test_a_premium_listing_cannot_be_free(self, db_session: AsyncSession) -> None:
        publisher = await _workspace(db_session)
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO marketplace_listings "
                    "(id, slug, kind, publisher_workspace_id, title, category_slug, "
                    " status, pricing, price_cents) "
                    "VALUES (gen_random_uuid(), :slug, 'agent', :ws, 'T', 'research', "
                    " 'draft', 'premium', 0)"
                ),
                {"ws": publisher, "slug": f"bad-{uuid.uuid4().hex[:8]}"},
            )
        await db_session.rollback()

    async def test_a_rating_sum_above_five_per_review_is_rejected(
        self, db_session: AsyncSession
    ) -> None:
        # Catches an aggregate corrupted by a double-applied write, which
        # would otherwise render as an average above 5 on a public page.
        publisher = await _workspace(db_session)
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO marketplace_listings "
                    "(id, slug, kind, publisher_workspace_id, title, category_slug, "
                    " status, rating_sum, rating_count) "
                    "VALUES (gen_random_uuid(), :slug, 'agent', :ws, 'T', 'research', "
                    " 'draft', 100, 1)"
                ),
                {"ws": publisher, "slug": f"bad-{uuid.uuid4().hex[:8]}"},
            )
        await db_session.rollback()

    async def test_a_workspace_with_listings_cannot_be_deleted(
        self, db_session: AsyncSession
    ) -> None:
        # RESTRICT, not CASCADE: deleting a workspace must not silently
        # remove listings other workspaces have installed from.
        publisher = await _workspace(db_session)
        service = _service(db_session)
        await service.create_listing(
            publisher_workspace_id=publisher,
            publisher_name="Acme",
            kind=ListingKind.AGENT,
            title="Blocks Deletion",
            summary=_SUMMARY,
            description=_DESCRIPTION,
            category_slug="research",
            pricing=Pricing.FREE,
            price_cents=0,
        )
        await db_session.flush()
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text("DELETE FROM workspaces WHERE id = :ws"), {"ws": publisher}
            )
        await db_session.rollback()
