"""Repository ports for the marketplace context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agentverse_api.marketplace_service.domain.install import ImportedConfig, MarketplaceInstall
from agentverse_api.marketplace_service.domain.listing import (
    Listing,
    ListingKind,
    ListingStatus,
    Pricing,
)
from agentverse_api.marketplace_service.domain.review import RatingAggregate, Review


@dataclass(frozen=True, slots=True)
class Category:
    slug: str
    name: str
    description: str
    sort_order: int


@dataclass(frozen=True, slots=True)
class ListingVersion:
    id: str
    listing_id: str
    version_number: int
    config: dict[str, object]
    changelog: str
    source_agent_version_id: str | None
    created_at: str


class CatalogSort(Protocol):
    """Marker for the sort orders the catalog exposes. See `SortOrder`."""


class ListingRepository(Protocol):
    """The catalog.

    `browse` is the one read in this context that does **not** filter by
    workspace — a published listing is public, and scoping it to the
    viewer would mean every workspace saw only its own agents. Every
    other method either takes an explicit `publisher_workspace_id` or is
    called behind `domain.listing.may_view`.
    """

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
        """Published listings only, with a total for pagination.

        The total is returned alongside rather than left to a second
        call: a catalog page needs both, and two round trips can
        disagree if a listing is published between them.
        """
        ...

    async def get_by_slug(self, slug: str) -> Listing | None: ...

    async def get_by_id(self, listing_id: str) -> Listing | None: ...

    async def list_for_publisher(self, *, publisher_workspace_id: str, limit: int) -> list[Listing]:
        """Every listing this workspace owns, in any status — including
        the drafts and rejections `browse` must never return.
        """
        ...

    async def list_by_status(self, *, status: ListingStatus, limit: int) -> list[Listing]:
        """Across every workspace, for the moderation queue.

        The only other unscoped read in this context, and unlike `browse`
        it is not public: it is reachable solely behind
        `require_platform_admin`, because it deliberately returns
        listings nobody outside the publishing workspace may otherwise
        see.
        """
        ...

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
    ) -> Listing: ...

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
    ) -> Listing: ...

    async def set_status(
        self,
        *,
        listing_id: str,
        status: ListingStatus,
        moderation_note: str | None = None,
    ) -> Listing: ...

    async def set_featured(self, *, listing_id: str, is_featured: bool) -> Listing: ...

    async def record_install(self, listing_id: str) -> None:
        """Increment in SQL, never read-modify-write.

        Two concurrent installs would otherwise both read the same count
        and the listing would undercount — on the number the catalog
        sorts by.
        """
        ...

    async def set_rating_aggregate(
        self, *, listing_id: str, aggregate: RatingAggregate
    ) -> None: ...

    async def slug_exists(self, slug: str) -> bool: ...


class ListingVersionRepository(Protocol):
    async def publish_version(
        self,
        *,
        listing_id: str,
        version_number: int,
        config: dict[str, object],
        changelog: str,
        source_agent_version_id: str | None,
    ) -> ListingVersion: ...

    async def list_versions(self, listing_id: str) -> list[ListingVersion]: ...

    async def get_version(
        self, *, listing_id: str, version_number: int | None
    ) -> ListingVersion | None:
        """`version_number=None` returns the latest.

        Installing without naming a version should get the current one,
        and making every caller look up `latest_version` first would be
        two queries and a race.
        """
        ...


class ReviewRepository(Protocol):
    async def list_for_listing(self, *, listing_id: str, limit: int) -> list[Review]: ...

    async def get_for_workspace(
        self, *, listing_id: str, reviewer_workspace_id: str
    ) -> Review | None: ...

    async def upsert(
        self,
        *,
        listing_id: str,
        reviewer_workspace_id: str,
        reviewer_name: str,
        rating: int,
        body: str,
    ) -> tuple[Review, int | None]:
        """Write the review, returning it and the rating it replaced.

        The previous rating comes back because the caller needs it to
        move the denormalized aggregate correctly — an edit shifts the
        sum without touching the count, and treating it as a new review
        would let one reviewer weight the average by editing repeatedly.
        """
        ...

    async def delete(self, *, listing_id: str, reviewer_workspace_id: str) -> int | None:
        """Returns the removed rating, or `None` if there was none."""
        ...

    async def all_ratings(self, listing_id: str) -> list[int]:
        """Every rating, for reconciling the denormalized aggregate."""
        ...


class CategoryRepository(Protocol):
    async def list_active(self) -> list[Category]: ...

    async def exists(self, slug: str) -> bool: ...


class InstallRepository(Protocol):
    """Provenance records — which listing became which agent, where.

    Every method is workspace-scoped. This *is* a tenant-owned table, so
    the catalog's public-read exception does not extend to it: a
    workspace's install history is nobody else's business.
    """

    async def get(
        self, *, workspace_id: str, listing_id: str, version_number: int
    ) -> MarketplaceInstall | None: ...

    async def list_for_workspace(
        self, *, workspace_id: str, limit: int
    ) -> list[MarketplaceInstall]: ...

    async def record(
        self,
        *,
        workspace_id: str,
        listing_id: str,
        version_number: int,
        agent_id: str,
        installed_by_user_id: str,
    ) -> MarketplaceInstall:
        """Write, or re-point an existing record at a fresh agent.

        Upserted on `(workspace_id, listing_id, version_number)` so a
        double-clicked install cannot produce two agents, while installing
        a *newer* version still records separately — that is the
        difference between a retry and an upgrade.
        """
        ...

    async def count_for_listing(self, listing_id: str) -> int:
        """For reconciling the catalog's denormalized install count."""
        ...


class AgentImporter(Protocol):
    """Creates the installed agent, on the other side of a context
    boundary.

    The marketplace does not write `agents`/`agent_versions` — those are
    the orchestration context's tables, and reaching into them directly
    is exactly what Rule 5 forbids. This port is the whole of what the
    marketplace needs from that context, and the composition root binds
    it to orchestration's own use case.
    """

    async def create_from_listing(
        self,
        *,
        workspace_id: str,
        name: str,
        description: str,
        created_by_user_id: str,
        config: ImportedConfig,
    ) -> str:
        """Returns the new agent's id."""
        ...

    async def exists(self, *, workspace_id: str, agent_id: str) -> bool:
        """Whether a previously installed agent is still there.

        Asked before returning an existing install as a no-op: a record
        pointing at an agent the installer has since deleted should
        install again, not hand back a dead id.
        """
        ...
