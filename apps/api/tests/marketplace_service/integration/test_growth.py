"""Phase 11's growth loop, end to end: sharing a listing writes an audit
event, installing one moves the catalog counter, and `/growth/metrics`
reports both back to the workspace that generated them — real Postgres,
real app, mirroring `test_workspace_referral_attribution.py`'s
`make_client` pattern.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.infrastructure.models import User
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
    get_current_identity_optional,
)
from agentverse_api.infrastructure.db import get_db_session
from agentverse_api.main import create_app
from agentverse_api.marketplace_service.application.marketplace_service import MarketplaceService
from agentverse_api.marketplace_service.domain.listing import ListingKind, Pricing
from agentverse_api.marketplace_service.infrastructure.repositories import (
    SqlCategoryRepository,
    SqlListingRepository,
    SqlListingVersionRepository,
    SqlReviewRepository,
)

pytestmark = pytest.mark.integration

_SUMMARY = "A genuinely useful research agent for teams that need citations."
_DESCRIPTION = "x" * 200
_CONFIG: dict[str, object] = {
    "model": "gpt-4o-mini",
    "system_instructions": "Research things and cite sources.",
}


async def _make_user(session: AsyncSession, user_id: str) -> None:
    session.add(
        User(
            id=user_id,
            name=user_id,
            email=f"{user_id}@example.com",
            email_verified=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    await session.commit()


async def _publish(session: AsyncSession, publisher: str) -> str:
    service = MarketplaceService(
        listings=SqlListingRepository(session),
        versions=SqlListingVersionRepository(session),
        reviews=SqlReviewRepository(session),
        categories=SqlCategoryRepository(session),
    )
    listing = await service.create_listing(
        publisher_workspace_id=publisher,
        publisher_name="Acme",
        kind=ListingKind.AGENT,
        title=f"Shareable {uuid.uuid4().hex[:8]}",
        summary=_SUMMARY,
        description=_DESCRIPTION,
        category_slug="research",
        pricing=Pricing.FREE,
        price_cents=0,
    )
    await service.publish_version(
        slug=listing.slug, actor_workspace_id=publisher, config=dict(_CONFIG), changelog="v1"
    )
    await service.submit_for_review(slug=listing.slug, actor_workspace_id=publisher)
    await service.approve(listing_id=listing.id)
    return listing.slug


@pytest.fixture
async def make_client(
    db_session: AsyncSession,
) -> AsyncIterator[Callable[[str], AsyncClient]]:
    clients: list[AsyncClient] = []

    async def db_session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    def factory(user_id: str) -> AsyncClient:
        app = create_app()
        app.dependency_overrides[get_db_session] = db_session_override
        app.dependency_overrides[get_current_identity] = lambda: user_id
        app.dependency_overrides[get_current_identity_optional] = lambda: user_id
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        return client

    yield factory

    for client in clients:
        await client.aclose()


async def test_sharing_a_listing_shows_up_in_growth_metrics(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    user_id = f"user-{unique_name}"
    await _make_user(db_session, user_id)
    client = make_client(user_id)

    create = await client.post("/api/v1/workspaces", json={"name": f"ws-{unique_name}"})
    assert create.status_code == 201
    workspace_id = create.json()["id"]
    slug = await _publish(db_session, workspace_id)

    share = await client.post(
        f"/api/v1/workspaces/{workspace_id}/marketplace/listings/{slug}/share"
    )
    assert share.status_code == 204

    metrics = await client.get(f"/api/v1/workspaces/{workspace_id}/growth/metrics")
    assert metrics.status_code == 200
    body = metrics.json()
    assert body["marketplace_shares"] == 1
    assert body["marketplace_installs"] == 0
    assert len(body["referral_code"]) == 8


async def test_sharing_an_unknown_listing_is_404(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    user_id = f"user-{unique_name}"
    await _make_user(db_session, user_id)
    client = make_client(user_id)

    create = await client.post("/api/v1/workspaces", json={"name": f"ws-{unique_name}"})
    workspace_id = create.json()["id"]

    share = await client.post(
        f"/api/v1/workspaces/{workspace_id}/marketplace/listings/no-such-listing/share"
    )
    assert share.status_code == 404


async def test_installs_across_this_workspaces_listings_are_summed(
    db_session: AsyncSession,
    make_client: Callable[[str], AsyncClient],
    unique_name: str,
) -> None:
    publisher_user = f"publisher-{unique_name}"
    installer_user = f"installer-{unique_name}"
    await _make_user(db_session, publisher_user)
    await _make_user(db_session, installer_user)
    publisher_client = make_client(publisher_user)
    installer_client = make_client(installer_user)

    create_publisher = await publisher_client.post(
        "/api/v1/workspaces", json={"name": f"pub-{unique_name}"}
    )
    publisher_workspace_id = create_publisher.json()["id"]
    slug = await _publish(db_session, publisher_workspace_id)

    create_installer = await installer_client.post(
        "/api/v1/workspaces", json={"name": f"ins-{unique_name}"}
    )
    installer_workspace_id = create_installer.json()["id"]
    install = await installer_client.post(
        f"/api/v1/workspaces/{installer_workspace_id}/marketplace/listings/{slug}/install",
        json={},
    )
    assert install.status_code == 201

    metrics = await publisher_client.get(
        f"/api/v1/workspaces/{publisher_workspace_id}/growth/metrics"
    )
    assert metrics.json()["marketplace_installs"] == 1
