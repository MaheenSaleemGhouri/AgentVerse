"""Ratings and reviews.

Pure. The arithmetic here decides what number sits under every listing
in the catalog, which is the single most load-bearing signal in a
marketplace — it is what someone decides to install on.

**One review per workspace per listing.** Not per user: a workspace with
eight members could otherwise post eight reviews of a competitor's
listing, and the aggregate a stranger reads would be whatever the
largest team decided. Enforced by a unique index, not by an application
check, because two concurrent submissions would both pass the check.

**The aggregate is denormalized, and the tradeoff is deliberate.**
`rating_sum` and `rating_count` live on the listing rather than being
computed from the reviews on every catalog render. Averaging over a
listing's whole review history for every card on every page is the query
that stops being cheap first. The cost is that the two can drift, so
they are only ever written in the same transaction as the review that
changes them, and `recompute_from` exists to prove they have not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

#: Whole stars only. A half-star scale invites "3.5" to mean different
#: things to different reviewers, and the aggregate already gives the
#: fractional resolution anyone needs.
MIN_RATING = 1
MAX_RATING = 5


class InvalidRatingError(ValueError):
    """A rating outside the scale. Raised rather than clamped.

    Clamping a 7 to a 5 would silently record something the reviewer did
    not say, and the caller that produced it has a bug worth surfacing.
    """

    def __init__(self, rating: int) -> None:
        self.rating = rating
        super().__init__(f"Rating must be between {MIN_RATING} and {MAX_RATING}, got {rating}")


class SelfReviewError(Exception):
    """A workspace reviewing its own listing. Maps to HTTP 422.

    Refused at write time rather than filtered at read time: a
    self-review that exists but is hidden still has to be excluded from
    the aggregate by every consumer, and one of them will forget.
    """

    def __init__(self, listing_id: str) -> None:
        self.listing_id = listing_id
        super().__init__("A workspace cannot review its own listing")


def validate_rating(rating: int) -> int:
    if not MIN_RATING <= rating <= MAX_RATING:
        raise InvalidRatingError(rating)
    return rating


@dataclass(frozen=True, slots=True)
class Review:
    id: str
    listing_id: str
    #: The reviewing workspace. Reviews are attributed to a workspace,
    #: not a person — the display name is the workspace's, so an
    #: individual's name is never published to a public catalog page they
    #: did not choose to appear on.
    reviewer_workspace_id: str
    reviewer_name: str
    rating: int
    body: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RatingAggregate:
    """A listing's rating totals after a change."""

    rating_sum: int
    rating_count: int

    @property
    def average(self) -> float | None:
        if self.rating_count == 0:
            return None
        return round(self.rating_sum / self.rating_count, 2)


def apply_new_review(*, current: RatingAggregate, rating: int) -> RatingAggregate:
    validate_rating(rating)
    return RatingAggregate(
        rating_sum=current.rating_sum + rating,
        rating_count=current.rating_count + 1,
    )


def apply_updated_review(
    *, current: RatingAggregate, previous_rating: int, new_rating: int
) -> RatingAggregate:
    """Editing a review moves the sum, never the count.

    The obvious bug this exists to prevent: treating an edit as a new
    review, which inflates the count and lets one reviewer weight the
    average by editing repeatedly.
    """
    validate_rating(new_rating)
    return RatingAggregate(
        rating_sum=current.rating_sum - previous_rating + new_rating,
        rating_count=current.rating_count,
    )


def apply_removed_review(*, current: RatingAggregate, rating: int) -> RatingAggregate:
    """Floored at zero on both fields.

    A negative count is unrepresentable in a healthy system, but a
    removal applied twice — a retried delete — would produce one. The
    floor makes the retry harmless rather than corrupting the aggregate
    that every catalog page reads.
    """
    return RatingAggregate(
        rating_sum=max(0, current.rating_sum - rating),
        rating_count=max(0, current.rating_count - 1),
    )


def recompute_from(ratings: list[int]) -> RatingAggregate:
    """The aggregate re-derived from every review.

    Used by reconciliation to prove the denormalized columns have not
    drifted from the rows they summarise. It should always agree; a
    disagreement means something wrote an aggregate outside the
    transaction that owns it.
    """
    return RatingAggregate(rating_sum=sum(ratings), rating_count=len(ratings))
