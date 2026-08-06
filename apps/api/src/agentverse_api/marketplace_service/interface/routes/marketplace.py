"""`/api/v1/marketplace` — the public catalog, and publishing into it.

**Two authentication postures in one router, deliberately.**

The catalog reads (`GET /marketplace/listings`, `/categories`,
`/listings/{slug}`) are **unauthenticated**. A marketplace is a
marketing surface: it has to be readable by someone deciding whether to
sign up, and indexable. That is the same reasoning `/api/v1/plans`
already uses for published pricing.

Everything that publishes or reviews is workspace-scoped and goes
through `require_member` or `require_admin`, and `workspace_id` comes
from the authenticated context — never from the path or body (Rule 6).

The unauthenticated reads return only `published` listings. Draft and
rejected listings are filtered in the service by
`domain.listing.may_view`, and a listing the caller may not see answers
**404, not 403**, so unpublished work cannot be enumerated by probing
slugs.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from agentverse_api.auth_service.application.workspace_service import WorkspaceService
from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_admin,
    require_member,
)
from agentverse_api.auth_service.interface.dependencies.services import get_workspace_service
from agentverse_api.marketplace_service.application.marketplace_service import (
    ListingForbiddenError,
    ListingNotFoundError,
    MarketplaceService,
    SlugTakenError,
    UnknownCategoryError,
    WorkflowListingsNotYetSupportedError,
)
from agentverse_api.marketplace_service.domain.listing import (
    InvalidListingTransitionError,
    Listing,
    ListingKind,
    ListingNotPublishableError,
    Pricing,
)
from agentverse_api.marketplace_service.domain.review import (
    InvalidRatingError,
    SelfReviewError,
)
from agentverse_api.marketplace_service.interface.dependencies.services import (
    get_marketplace_service,
)

router = APIRouter(prefix="/api/v1/marketplace", tags=["marketplace"])


class CategoryResponse(BaseModel):
    slug: str
    name: str
    description: str


class ListingResponse(BaseModel):
    id: str
    slug: str
    kind: str
    publisher_name: str
    title: str
    summary: str
    description: str
    category_slug: str
    status: str
    pricing: str
    price_cents: int
    #: `null` with no reviews, never 0.0 — "not yet rated" and "rated
    #: badly" are different facts, and a client must be able to tell
    #: them apart.
    average_rating: float | None
    rating_count: int
    install_count: int
    is_featured: bool
    latest_version: int
    published_at: datetime | None


class ListingPageResponse(BaseModel):
    data: list[ListingResponse]
    #: Sent with the page so the client does not need a second request,
    #: and so it cannot disagree with the rows it was computed alongside.
    total: int


class ListingVersionResponse(BaseModel):
    version_number: int
    changelog: str
    created_at: str


class ReviewResponse(BaseModel):
    id: str
    #: The reviewing *workspace*, not the individual. A review appears on
    #: a public page and an individual's name should not land there.
    reviewer_name: str
    rating: int
    body: str
    created_at: datetime


class CreateListingRequest(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    summary: str = Field(default="", max_length=280)
    description: str = Field(default="", max_length=20_000)
    category_slug: str = Field(min_length=1, max_length=64)
    kind: ListingKind = ListingKind.AGENT
    pricing: Pricing = Pricing.FREE
    price_cents: int = Field(default=0, ge=0)
    slug: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9-]+$")


class UpdateListingRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=120)
    summary: str | None = Field(default=None, max_length=280)
    description: str | None = Field(default=None, max_length=20_000)
    category_slug: str | None = Field(default=None, max_length=64)
    pricing: Pricing | None = None
    price_cents: int | None = Field(default=None, ge=0)


class PublishVersionRequest(BaseModel):
    config: dict[str, object]
    changelog: str = Field(default="", max_length=2_000)
    source_agent_version_id: str | None = Field(default=None, max_length=64)


class SubmitReviewRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    body: str = Field(default="", max_length=4_000)


async def _publisher_name(workspaces: WorkspaceService, workspace_id: str) -> str:
    """The workspace's display name, for denormalizing onto the listing.

    Resolved through `auth_service`'s application service rather than by
    reading the `workspaces` table from this context (Rule 5). Falls back
    to the id only if the workspace vanished between the permission check
    and here — a catalog card showing an id is bad, but a 500 on publish
    is worse.
    """
    workspace = await workspaces.get_workspace(workspace_id)
    return workspace.name if workspace is not None else workspace_id


def _to_response(listing: Listing) -> ListingResponse:
    return ListingResponse(
        id=listing.id,
        slug=listing.slug,
        kind=listing.kind.value,
        publisher_name=listing.publisher_name,
        title=listing.title,
        summary=listing.summary,
        description=listing.description,
        category_slug=listing.category_slug,
        status=listing.status.value,
        pricing=listing.pricing.value,
        price_cents=listing.price_cents,
        average_rating=listing.average_rating,
        rating_count=listing.rating_count,
        install_count=listing.install_count,
        is_featured=listing.is_featured,
        latest_version=listing.latest_version,
        published_at=listing.published_at,
    )


# ---- public catalog ---------------------------------------------------


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories_route(
    service: MarketplaceService = Depends(get_marketplace_service),
) -> list[CategoryResponse]:
    """Unauthenticated: the category rail is part of the public catalog."""
    return [
        CategoryResponse(slug=c.slug, name=c.name, description=c.description)
        for c in await service.list_categories()
    ]


@router.get("/listings", response_model=ListingPageResponse)
async def browse_route(
    service: MarketplaceService = Depends(get_marketplace_service),
    category: str | None = Query(default=None, max_length=64),
    kind: ListingKind | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    featured: bool = Query(default=False),
    free: bool = Query(default=False),
    # A closed set, not free text: this reaches an ORDER BY, and an
    # unvalidated value there is an injection point. Unknown values fall
    # back to the default in the repository rather than reaching SQL.
    sort: str = Query(default="popular", pattern=r"^(popular|newest|rating|name)$"),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ListingPageResponse:
    """The public catalog. Published listings only, across every
    workspace — the one read in this platform that is deliberately not
    tenant-scoped.
    """
    listings, total = await service.browse(
        category_slug=category,
        kind=kind,
        query=q,
        featured_only=featured,
        free_only=free,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return ListingPageResponse(data=[_to_response(listing) for listing in listings], total=total)


@router.get("/listings/{slug}", response_model=ListingResponse)
async def get_listing_route(
    slug: str,
    service: MarketplaceService = Depends(get_marketplace_service),
) -> ListingResponse:
    """Unauthenticated, so it returns published listings only.

    A publisher viewing their own draft reads it through
    `/workspaces/{id}/marketplace/listings` instead, where they have a
    workspace context to be checked against.
    """
    try:
        listing = await service.get(slug=slug, viewer_workspace_id=None)
    except ListingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such listing"
        ) from exc
    return _to_response(listing)


@router.get("/listings/{slug}/versions", response_model=list[ListingVersionResponse])
async def list_versions_route(
    slug: str,
    service: MarketplaceService = Depends(get_marketplace_service),
) -> list[ListingVersionResponse]:
    try:
        versions = await service.versions_of(slug=slug, viewer_workspace_id=None)
    except ListingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such listing"
        ) from exc
    return [
        ListingVersionResponse(
            version_number=v.version_number,
            changelog=v.changelog,
            created_at=v.created_at,
        )
        for v in versions
    ]


@router.get("/listings/{slug}/reviews", response_model=list[ReviewResponse])
async def list_reviews_route(
    slug: str,
    service: MarketplaceService = Depends(get_marketplace_service),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ReviewResponse]:
    try:
        reviews = await service.list_reviews(slug=slug, viewer_workspace_id=None, limit=limit)
    except ListingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such listing"
        ) from exc
    return [
        ReviewResponse(
            id=r.id,
            reviewer_name=r.reviewer_name,
            rating=r.rating,
            body=r.body,
            created_at=r.created_at,
        )
        for r in reviews
    ]


# ---- publishing (workspace-scoped) ------------------------------------

publisher_router = APIRouter(prefix="/api/v1/workspaces", tags=["marketplace-publishing"])


@publisher_router.get("/{workspace_id}/marketplace/listings", response_model=list[ListingResponse])
async def list_my_listings_route(
    context: WorkspaceContext = Depends(require_member),
    service: MarketplaceService = Depends(get_marketplace_service),
) -> list[ListingResponse]:
    """This workspace's listings in *every* status, including the drafts
    and rejections the public catalog must never return.
    """
    listings = await service.list_mine(publisher_workspace_id=context.workspace_id)
    return [_to_response(listing) for listing in listings]


@publisher_router.post(
    "/{workspace_id}/marketplace/listings",
    response_model=ListingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_listing_route(
    body: CreateListingRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: MarketplaceService = Depends(get_marketplace_service),
    workspaces: WorkspaceService = Depends(get_workspace_service),
) -> ListingResponse:
    """Create a draft. `require_admin`, because publishing puts the
    workspace's name on a public page.
    """
    try:
        listing = await service.create_listing(
            publisher_workspace_id=context.workspace_id,
            # Denormalized onto the listing so a catalog page renders
            # without joining `workspaces`. The workspace's own name, not
            # the acting user's — a person's name should not land on a
            # public page because they clicked publish.
            publisher_name=await _publisher_name(workspaces, context.workspace_id),
            kind=body.kind,
            title=body.title,
            summary=body.summary,
            description=body.description,
            category_slug=body.category_slug,
            pricing=body.pricing,
            price_cents=body.price_cents,
            slug=body.slug,
        )
    except WorkflowListingsNotYetSupportedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except UnknownCategoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except SlugTakenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_response(listing)


@publisher_router.patch(
    "/{workspace_id}/marketplace/listings/{slug}", response_model=ListingResponse
)
async def update_listing_route(
    slug: str,
    body: UpdateListingRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: MarketplaceService = Depends(get_marketplace_service),
) -> ListingResponse:
    try:
        listing = await service.update_listing(
            slug=slug,
            actor_workspace_id=context.workspace_id,
            title=body.title,
            summary=body.summary,
            description=body.description,
            category_slug=body.category_slug,
            pricing=body.pricing,
            price_cents=body.price_cents,
        )
    except ListingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such listing"
        ) from exc
    except ListingForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except UnknownCategoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _to_response(listing)


@publisher_router.post(
    "/{workspace_id}/marketplace/listings/{slug}/versions",
    response_model=ListingVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def publish_version_route(
    slug: str,
    body: PublishVersionRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: MarketplaceService = Depends(get_marketplace_service),
) -> ListingVersionResponse:
    """Snapshot a configuration as a new version.

    The config is *copied*. The publisher can delete their source agent
    afterwards and every install made from this version keeps working.
    """
    try:
        version = await service.publish_version(
            slug=slug,
            actor_workspace_id=context.workspace_id,
            config=body.config,
            changelog=body.changelog,
            source_agent_version_id=body.source_agent_version_id,
        )
    except ListingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such listing"
        ) from exc
    except ListingForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return ListingVersionResponse(
        version_number=version.version_number,
        changelog=version.changelog,
        created_at=version.created_at,
    )


@publisher_router.post(
    "/{workspace_id}/marketplace/listings/{slug}/submit", response_model=ListingResponse
)
async def submit_listing_route(
    slug: str,
    context: WorkspaceContext = Depends(require_admin),
    service: MarketplaceService = Depends(get_marketplace_service),
) -> ListingResponse:
    """Submit for moderation. Reports *every* readiness problem at once,
    so a publisher does not make three round trips to submit.
    """
    try:
        listing = await service.submit_for_review(
            slug=slug, actor_workspace_id=context.workspace_id
        )
    except ListingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such listing"
        ) from exc
    except ListingForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ListingNotPublishableError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "listing_not_ready", "problems": exc.reasons},
        ) from exc
    except InvalidListingTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_response(listing)


@publisher_router.post(
    "/{workspace_id}/marketplace/listings/{slug}/unlist", response_model=ListingResponse
)
async def unlist_listing_route(
    slug: str,
    context: WorkspaceContext = Depends(require_admin),
    service: MarketplaceService = Depends(get_marketplace_service),
) -> ListingResponse:
    """Withdraw from the catalog. Not deletion — installs already made
    from this listing are copies in other workspaces, and the row
    survives so their provenance stays explicable.
    """
    try:
        listing = await service.unlist(slug=slug, actor_workspace_id=context.workspace_id)
    except ListingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such listing"
        ) from exc
    except ListingForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except InvalidListingTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_response(listing)


@publisher_router.put(
    "/{workspace_id}/marketplace/listings/{slug}/review", response_model=ReviewResponse
)
async def submit_review_route(
    slug: str,
    body: SubmitReviewRequest,
    context: WorkspaceContext = Depends(require_member),
    service: MarketplaceService = Depends(get_marketplace_service),
    workspaces: WorkspaceService = Depends(get_workspace_service),
) -> ReviewResponse:
    """One review per workspace, so `PUT` rather than `POST` — a second
    submission replaces the first rather than adding one.
    """
    try:
        review = await service.submit_review(
            slug=slug,
            reviewer_workspace_id=context.workspace_id,
            reviewer_name=await _publisher_name(workspaces, context.workspace_id),
            rating=body.rating,
            body=body.body,
        )
    except ListingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such listing"
        ) from exc
    except SelfReviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except InvalidRatingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return ReviewResponse(
        id=review.id,
        reviewer_name=review.reviewer_name,
        rating=review.rating,
        body=review.body,
        created_at=review.created_at,
    )


@publisher_router.delete(
    "/{workspace_id}/marketplace/listings/{slug}/review",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def withdraw_review_route(
    slug: str,
    context: WorkspaceContext = Depends(require_member),
    service: MarketplaceService = Depends(get_marketplace_service),
) -> None:
    try:
        removed = await service.withdraw_review(
            slug=slug, reviewer_workspace_id=context.workspace_id
        )
    except ListingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such listing"
        ) from exc
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This workspace has not reviewed that listing.",
        )
