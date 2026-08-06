"""Marketplace visibility rules, moderation transitions and rating maths.

The visibility tests are the important ones. This is the only surface in
the platform where "filter by workspace_id" is *wrong*, so the rule that
replaces it has to be pinned down: published is public, everything else
is the publisher's alone.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agentverse_api.marketplace_service.domain.listing import (
    InvalidListingTransitionError,
    Listing,
    ListingKind,
    ListingStatus,
    Pricing,
    assert_transition,
    can_transition,
    is_public,
    may_edit,
    may_view,
    readiness_problems,
)
from agentverse_api.marketplace_service.domain.review import (
    InvalidRatingError,
    RatingAggregate,
    apply_new_review,
    apply_removed_review,
    apply_updated_review,
    recompute_from,
    validate_rating,
)

_T0 = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
_PUBLISHER = "ws-publisher"
_OTHER = "ws-other"


def _listing(
    *,
    status: ListingStatus = ListingStatus.PUBLISHED,
    summary: str = "A genuinely useful research agent for teams.",
    description: str = "x" * 200,
    pricing: Pricing = Pricing.FREE,
    price_cents: int = 0,
    rating_sum: int = 0,
    rating_count: int = 0,
) -> Listing:
    return Listing(
        id="listing-1",
        slug="research-agent",
        kind=ListingKind.AGENT,
        publisher_workspace_id=_PUBLISHER,
        publisher_name="Acme",
        title="Research Agent",
        summary=summary,
        description=description,
        category_slug="research",
        status=status,
        pricing=pricing,
        price_cents=price_cents,
        rating_sum=rating_sum,
        rating_count=rating_count,
        install_count=0,
        is_featured=False,
        latest_version=1,
        published_at=_T0,
        created_at=_T0,
        updated_at=_T0,
    )


class TestVisibility:
    def test_a_published_listing_is_visible_to_anyone_including_anonymous(self) -> None:
        # The catalog is a marketing surface; it has to be readable by
        # someone deciding whether to sign up.
        listing = _listing()
        assert may_view(listing=listing, viewer_workspace_id=None) is True
        assert may_view(listing=listing, viewer_workspace_id=_OTHER) is True

    def test_a_draft_is_visible_only_to_its_publisher(self) -> None:
        # Leaking one would expose work someone has not chosen to show.
        listing = _listing(status=ListingStatus.DRAFT)
        assert may_view(listing=listing, viewer_workspace_id=_PUBLISHER) is True
        assert may_view(listing=listing, viewer_workspace_id=_OTHER) is False
        assert may_view(listing=listing, viewer_workspace_id=None) is False

    def test_a_rejected_listing_is_visible_only_to_its_publisher(self) -> None:
        listing = _listing(status=ListingStatus.REJECTED)
        assert may_view(listing=listing, viewer_workspace_id=_PUBLISHER) is True
        assert may_view(listing=listing, viewer_workspace_id=_OTHER) is False

    def test_an_unlisted_listing_leaves_the_public_catalog(self) -> None:
        # Withdrawn, not deleted: installs made from it are copies in
        # other workspaces and keep working.
        listing = _listing(status=ListingStatus.UNLISTED)
        assert is_public(ListingStatus.UNLISTED) is False
        assert may_view(listing=listing, viewer_workspace_id=None) is False
        assert may_view(listing=listing, viewer_workspace_id=_PUBLISHER) is True

    def test_only_published_is_public(self) -> None:
        for status in ListingStatus:
            assert is_public(status) is (status is ListingStatus.PUBLISHED)

    def test_only_the_publisher_may_edit_even_a_public_listing(self) -> None:
        listing = _listing()
        assert may_edit(listing=listing, actor_workspace_id=_PUBLISHER) is True
        assert may_edit(listing=listing, actor_workspace_id=_OTHER) is False


class TestModeration:
    def test_a_draft_cannot_be_published_directly(self) -> None:
        # Skipping review would make moderation optional.
        assert not can_transition(current=ListingStatus.DRAFT, target=ListingStatus.PUBLISHED)

    def test_the_normal_path_is_draft_review_published(self) -> None:
        assert can_transition(current=ListingStatus.DRAFT, target=ListingStatus.PENDING_REVIEW)
        assert can_transition(current=ListingStatus.PENDING_REVIEW, target=ListingStatus.PUBLISHED)

    def test_a_rejected_listing_is_fixed_and_resubmitted(self) -> None:
        # Rather than recreated — so its reviews and install history
        # survive the correction.
        assert can_transition(current=ListingStatus.REJECTED, target=ListingStatus.PENDING_REVIEW)

    def test_unlisting_is_reversible(self) -> None:
        assert can_transition(current=ListingStatus.PUBLISHED, target=ListingStatus.UNLISTED)
        assert can_transition(current=ListingStatus.UNLISTED, target=ListingStatus.PUBLISHED)

    def test_moderation_can_pull_a_published_listing_back(self) -> None:
        assert can_transition(current=ListingStatus.PUBLISHED, target=ListingStatus.PENDING_REVIEW)

    def test_an_illegal_transition_raises_rather_than_silently_passing(self) -> None:
        with pytest.raises(InvalidListingTransitionError) as exc:
            assert_transition(current=ListingStatus.DRAFT, target=ListingStatus.PUBLISHED)
        assert exc.value.current is ListingStatus.DRAFT


class TestReadiness:
    def test_a_complete_listing_has_no_problems(self) -> None:
        assert readiness_problems(listing=_listing(), has_version=True) == []

    def test_every_problem_is_reported_at_once(self) -> None:
        # A publisher who fixes one issue and is told about the next
        # makes three round trips to submit.
        problems = readiness_problems(
            listing=_listing(summary="short", description="also short"),
            has_version=False,
        )
        assert len(problems) == 3

    def test_a_listing_with_no_version_cannot_be_submitted(self) -> None:
        problems = readiness_problems(listing=_listing(), has_version=False)
        assert any("nothing to install" in p for p in problems)

    def test_a_premium_listing_needs_a_price(self) -> None:
        problems = readiness_problems(
            listing=_listing(pricing=Pricing.PREMIUM, price_cents=0), has_version=True
        )
        assert any("price above zero" in p for p in problems)

    def test_a_free_listing_must_not_carry_a_price(self) -> None:
        # Otherwise a listing can claim to be free and still charge.
        problems = readiness_problems(
            listing=_listing(pricing=Pricing.FREE, price_cents=500), has_version=True
        )
        assert any("price of zero" in p for p in problems)


class TestAverageRating:
    def test_an_unreviewed_listing_has_no_rating_rather_than_zero(self) -> None:
        # Zero would sort an unreviewed listing below a badly-reviewed
        # one and render as a real score.
        assert _listing().average_rating is None

    def test_the_average_is_computed_from_the_aggregate(self) -> None:
        assert _listing(rating_sum=9, rating_count=2).average_rating == 4.5


class TestRatingArithmetic:
    def test_a_new_review_moves_both_sum_and_count(self) -> None:
        result = apply_new_review(current=RatingAggregate(rating_sum=8, rating_count=2), rating=5)
        assert result == RatingAggregate(rating_sum=13, rating_count=3)

    def test_an_edit_moves_the_sum_without_touching_the_count(self) -> None:
        # Treating an edit as a new review inflates the count and lets
        # one reviewer weight the average by editing repeatedly.
        result = apply_updated_review(
            current=RatingAggregate(rating_sum=13, rating_count=3),
            previous_rating=5,
            new_rating=2,
        )
        assert result == RatingAggregate(rating_sum=10, rating_count=3)

    def test_removing_a_review_reverses_it(self) -> None:
        result = apply_removed_review(
            current=RatingAggregate(rating_sum=13, rating_count=3), rating=5
        )
        assert result == RatingAggregate(rating_sum=8, rating_count=2)

    def test_a_repeated_removal_cannot_drive_the_aggregate_negative(self) -> None:
        # A retried delete would otherwise corrupt the number every
        # catalog page reads.
        result = apply_removed_review(
            current=RatingAggregate(rating_sum=0, rating_count=0), rating=5
        )
        assert result == RatingAggregate(rating_sum=0, rating_count=0)

    def test_a_rating_outside_the_scale_is_refused_not_clamped(self) -> None:
        # Clamping a 7 to a 5 records something the reviewer did not say.
        for bad in (0, 6, -1, 100):
            with pytest.raises(InvalidRatingError):
                validate_rating(bad)

    def test_every_rating_on_the_scale_is_accepted(self) -> None:
        for good in (1, 2, 3, 4, 5):
            assert validate_rating(good) == good

    def test_an_edit_to_an_invalid_rating_is_refused(self) -> None:
        with pytest.raises(InvalidRatingError):
            apply_updated_review(
                current=RatingAggregate(rating_sum=5, rating_count=1),
                previous_rating=5,
                new_rating=9,
            )

    def test_recompute_matches_incremental_application(self) -> None:
        # The property the denormalized aggregate depends on: applying
        # reviews one at a time must land where recomputing from all of
        # them does, or the two drift.
        ratings = [5, 3, 4, 1, 5]
        incremental = RatingAggregate(rating_sum=0, rating_count=0)
        for rating in ratings:
            incremental = apply_new_review(current=incremental, rating=rating)
        assert incremental == recompute_from(ratings)

    def test_recompute_of_nothing_is_empty_not_an_error(self) -> None:
        assert recompute_from([]) == RatingAggregate(rating_sum=0, rating_count=0)
        assert recompute_from([]).average is None
