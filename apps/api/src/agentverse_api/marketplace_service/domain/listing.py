"""The marketplace catalog: what is published, by whom, and in what state.

Pure — no I/O, no framework.

**The tenancy decision, stated first because it is the one that departs
from the platform's default.** Rule 11 makes `workspace_id` absolute:
every tenant-owned table carries it and every query filters by it. A
marketplace listing carries `publisher_workspace_id` — someone owns it,
and only they may edit it — but the *browse* query deliberately does
**not** filter by workspace. That is the entire point of a marketplace:
a published listing is public, and scoping the catalog to the viewer's
workspace would mean every workspace saw only its own agents.

So the rule here is narrower and must be applied deliberately:

- **Read of the catalog** — no workspace filter. Public by design.
- **Read of a draft or rejected listing** — filtered by
  `publisher_workspace_id`. An unpublished listing is private, and
  leaking one would expose work someone has not chosen to show.
- **Every write** — filtered by `publisher_workspace_id`. A workspace
  may only edit what it published.

`may_view` and `may_edit` below encode exactly that, so no route has to
re-derive it.

**A listing version is an immutable snapshot, not a link.** Installing
copies the configuration into the installing workspace. The publisher
can delete their source agent, change it beyond recognition, or leave
the platform, and every existing install keeps working — which is the
only way a marketplace can be trusted. `source_agent_version_id` is
recorded for provenance and deliberately carries no foreign key, because
the row it points at is allowed to disappear.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ListingKind(StrEnum):
    """What is being published.

    `WORKFLOW` exists in the schema from the start and is deliberately
    not yet reachable: the DAG workflow feature has not shipped, so
    there is nothing to publish. Modelling it now costs one CHECK value
    and means the marketplace does not need reshaping when it lands —
    but a publish route that accepted it today would offer a button for
    something a customer cannot create.
    """

    AGENT = "agent"
    WORKFLOW = "workflow"


class ListingStatus(StrEnum):
    """Where a listing is in its moderation life.

    `UNLISTED` is not deletion. A publisher who withdraws a listing must
    not break the installs already made from it, so the row and its
    version snapshots survive — it simply stops appearing in the
    catalog. Deleting would be the one action that reaches into other
    workspaces.
    """

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    UNLISTED = "unlisted"


#: Statuses whose listings appear in the public catalog.
_PUBLIC_STATUSES: frozenset[ListingStatus] = frozenset({ListingStatus.PUBLISHED})


class Pricing(StrEnum):
    FREE = "free"
    PREMIUM = "premium"


_TRANSITIONS: dict[tuple[ListingStatus, ListingStatus], bool] = {
    (ListingStatus.DRAFT, ListingStatus.PENDING_REVIEW): True,
    (ListingStatus.PENDING_REVIEW, ListingStatus.PUBLISHED): True,
    (ListingStatus.PENDING_REVIEW, ListingStatus.REJECTED): True,
    # A rejected listing is fixed and resubmitted rather than recreated,
    # so its reviews and install history survive the correction.
    (ListingStatus.REJECTED, ListingStatus.PENDING_REVIEW): True,
    (ListingStatus.PUBLISHED, ListingStatus.UNLISTED): True,
    (ListingStatus.UNLISTED, ListingStatus.PUBLISHED): True,
    # Moderation can pull a published listing back for re-review.
    (ListingStatus.PUBLISHED, ListingStatus.PENDING_REVIEW): True,
}


class InvalidListingTransitionError(Exception):
    """Maps to HTTP 409 — well-formed request, wrong current state."""

    def __init__(self, *, current: ListingStatus, target: ListingStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Cannot move a listing from {current.value!r} to {target.value!r}")


class ListingNotPublishableError(Exception):
    """The listing cannot be submitted as it stands. Maps to 422.

    Carries the specific reasons rather than a generic refusal: a
    publisher told "not ready" cannot act, and one told "needs a summary
    and at least one version" can.
    """

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("; ".join(reasons))


def can_transition(*, current: ListingStatus, target: ListingStatus) -> bool:
    return _TRANSITIONS.get((current, target), False)


def assert_transition(*, current: ListingStatus, target: ListingStatus) -> None:
    if not can_transition(current=current, target=target):
        raise InvalidListingTransitionError(current=current, target=target)


def is_public(status: ListingStatus) -> bool:
    return status in _PUBLIC_STATUSES


@dataclass(frozen=True, slots=True)
class Listing:
    """One published thing, as the rest of the system sees it."""

    id: str
    #: Globally unique and stable: it is the public URL, and changing it
    #: would break every link anyone has shared.
    slug: str
    kind: ListingKind
    publisher_workspace_id: str
    publisher_name: str
    title: str
    summary: str
    description: str
    category_slug: str
    status: ListingStatus
    pricing: Pricing
    #: Integer cents (Rule 15). Zero for a free listing — never null,
    #: because "no price" and "free" are the same thing here and two
    #: representations of it would need branching at every call site.
    price_cents: int
    #: Denormalized aggregates. Kept in sync inside the same transaction
    #: as the review that changes them (see `review.py`), because
    #: recomputing an average over every review on each catalog render
    #: is the query that stops being cheap first.
    rating_sum: int
    rating_count: int
    install_count: int
    #: Curated placement. A listing is featured by a platform admin, not
    #: by its publisher — otherwise every publisher features themselves.
    is_featured: bool
    latest_version: int
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    #: First-party: a template from the built-in library rather than a
    #: customer's submission — published by the platform workspace,
    #: always free, and never moderated. Set only by the seed migration;
    #: no route can turn it on, because "we wrote this" is not a claim a
    #: publisher gets to make about themselves.
    #:
    #: Last and defaulted so existing construction sites are unchanged.
    is_official: bool = False

    @property
    def average_rating(self) -> float | None:
        """`None` with no reviews, never 0.0.

        Zero would sort an unreviewed listing below a badly-reviewed one
        and render as a real score. "Not yet rated" is a different fact
        from "rated badly", and the UI has to be able to tell them
        apart.
        """
        if self.rating_count == 0:
            return None
        return round(self.rating_sum / self.rating_count, 2)

    @property
    def is_free(self) -> bool:
        return self.pricing is Pricing.FREE or self.price_cents == 0


def may_view(*, listing: Listing, viewer_workspace_id: str | None) -> bool:
    """Can this viewer see this listing at all?

    Published listings are public, including to anonymous visitors — the
    catalog is a marketing surface. Anything else is visible only to the
    workspace that published it.
    """
    if is_public(listing.status):
        return True
    return viewer_workspace_id is not None and (
        viewer_workspace_id == listing.publisher_workspace_id
    )


def may_edit(*, listing: Listing, actor_workspace_id: str) -> bool:
    """Only the publishing workspace edits its own listing.

    Moderation actions (approve, reject, feature) are a different
    authority and do not go through here — they are platform-admin
    operations, and conflating them would let a publisher approve
    themselves.
    """
    return actor_workspace_id == listing.publisher_workspace_id


#: Minimum lengths for a listing anyone would install. Enforced at
#: submission rather than at draft creation, so a publisher can save
#: work in progress without fighting validation.
_MIN_SUMMARY = 20
_MIN_DESCRIPTION = 100


def readiness_problems(*, listing: Listing, has_version: bool) -> list[str]:
    """Everything blocking submission, all at once.

    Returns every problem rather than the first, because a publisher who
    fixes one issue and is told about the next has to make three round
    trips to submit.
    """
    problems: list[str] = []
    if len(listing.summary.strip()) < _MIN_SUMMARY:
        problems.append(
            f"Summary must be at least {_MIN_SUMMARY} characters — it is the one line "
            "shown on the catalog card."
        )
    if len(listing.description.strip()) < _MIN_DESCRIPTION:
        problems.append(
            f"Description must be at least {_MIN_DESCRIPTION} characters — someone "
            "deciding whether to install this needs to know what it does."
        )
    if not has_version:
        problems.append(
            "Publish at least one version — a listing with no version has nothing to install."
        )
    if listing.pricing is Pricing.PREMIUM and listing.price_cents <= 0:
        problems.append("A premium listing needs a price above zero.")
    if listing.pricing is Pricing.FREE and listing.price_cents != 0:
        problems.append("A free listing must have a price of zero.")
    return problems
