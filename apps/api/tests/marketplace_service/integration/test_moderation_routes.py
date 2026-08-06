"""The moderation surface, end to end through the real app.

This is the one route group in the platform whose authority is not a
workspace role, so the tests that matter are about who can reach it. A
publisher who can approve their own listing has made moderation
decorative, and the failure would be silent — the listing simply appears
in the public catalog.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.infrastructure.models import AuditLog, PlatformAdmin, User
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
    get_current_identity_optional,
)
from agentverse_api.infrastructure.db import get_db_session
from agentverse_api.main import create_app

pytestmark = pytest.mark.integration

_SUMMARY = "A genuinely useful research agent for teams that need citations."
_DESCRIPTION = "x" * 200
_CONFIG = {"model": "gpt-4o-mini", "system_instructions": "Research and cite."}


async def _make_user(session: AsyncSession, user_id: str) -> None:
    session.add(
        User(
            id=user_id,
            name=user_id,
            email=f"{user_id}@example.com",
            email_verified=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    await session.commit()


async def _make_platform_admin(session: AsyncSession, user_id: str) -> None:
    session.add(PlatformAdmin(user_id=user_id, note="test", created_at=datetime.now(UTC)))
    await session.commit()


@pytest.fixture
async def make_client(db_session: AsyncSession) -> AsyncIterator[Callable[[str], AsyncClient]]:
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


async def _submitted_listing(client: AsyncClient, workspace_id: str) -> dict[str, object]:
    """A listing carried to `pending_review` by its publisher."""
    created = await client.post(
        f"/api/v1/workspaces/{workspace_id}/marketplace/listings",
        json={
            "title": f"Moderated {uuid.uuid4().hex[:8]}",
            "summary": _SUMMARY,
            "description": _DESCRIPTION,
            "category_slug": "research",
        },
    )
    assert created.status_code == 201, created.text
    listing = created.json()
    slug = listing["slug"]

    version = await client.post(
        f"/api/v1/workspaces/{workspace_id}/marketplace/listings/{slug}/versions",
        json={"config": _CONFIG, "changelog": "v1"},
    )
    assert version.status_code == 201, version.text

    submitted = await client.post(
        f"/api/v1/workspaces/{workspace_id}/marketplace/listings/{slug}/submit", json={}
    )
    assert submitted.status_code == 200, submitted.text
    return submitted.json()


async def _workspace(client: AsyncClient, name: str) -> str:
    created = await client.post("/api/v1/workspaces", json={"name": name})
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


class TestWhoCanModerate:
    async def test_a_publisher_cannot_approve_their_own_listing(
        self,
        db_session: AsyncSession,
        make_client: Callable[[str], AsyncClient],
        unique_name: str,
    ) -> None:
        # The failure this whole authority exists to prevent. If it
        # passed, moderation would be decorative and the listing would
        # simply appear in the public catalog.
        publisher_user = f"publisher-{unique_name}"
        await _make_user(db_session, publisher_user)
        client = make_client(publisher_user)
        workspace = await _workspace(client, f"ws-{unique_name}")
        listing = await _submitted_listing(client, workspace)

        response = await client.post(
            f"/api/v1/admin/marketplace/listings/{listing['id']}/approve", json={}
        )

        assert response.status_code == 404
        await db_session.rollback()

    async def test_an_ordinary_user_gets_404_rather_than_403(
        self,
        db_session: AsyncSession,
        make_client: Callable[[str], AsyncClient],
        unique_name: str,
    ) -> None:
        # 404, so the moderation surface does not confirm its own
        # existence to someone with no business there — the same
        # reasoning `get_current_workspace` applies to workspaces.
        user = f"nobody-{unique_name}"
        await _make_user(db_session, user)
        client = make_client(user)

        response = await client.get("/api/v1/admin/marketplace/queue")

        assert response.status_code == 404
        await db_session.rollback()

    async def test_a_denial_is_audit_logged(
        self,
        db_session: AsyncSession,
        make_client: Callable[[str], AsyncClient],
        unique_name: str,
    ) -> None:
        # Written from the enforcement point, so no route can forget it.
        user = f"denied-{unique_name}"
        await _make_user(db_session, user)
        client = make_client(user)

        await client.get("/api/v1/admin/marketplace/queue")

        result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.actor_user_id == user,
                AuditLog.action == "platform_admin.denied",
            )
        )
        assert result.scalars().first() is not None
        await db_session.rollback()

    async def test_a_platform_admin_reaches_the_queue(
        self,
        db_session: AsyncSession,
        make_client: Callable[[str], AsyncClient],
        unique_name: str,
    ) -> None:
        admin = f"admin-{unique_name}"
        await _make_user(db_session, admin)
        await _make_platform_admin(db_session, admin)

        response = await make_client(admin).get("/api/v1/admin/marketplace/queue")

        assert response.status_code == 200
        assert isinstance(response.json(), list)
        await db_session.rollback()


class TestModerationDecisions:
    async def test_an_admin_approving_publishes_the_listing(
        self,
        db_session: AsyncSession,
        make_client: Callable[[str], AsyncClient],
        unique_name: str,
    ) -> None:
        publisher_user = f"publisher-{unique_name}"
        admin = f"admin-{unique_name}"
        await _make_user(db_session, publisher_user)
        await _make_user(db_session, admin)
        await _make_platform_admin(db_session, admin)

        publisher_client = make_client(publisher_user)
        workspace = await _workspace(publisher_client, f"ws-{unique_name}")
        listing = await _submitted_listing(publisher_client, workspace)

        response = await make_client(admin).post(
            f"/api/v1/admin/marketplace/listings/{listing['id']}/approve",
            json={"note": "Looks good."},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "published"

        # And it is now in the public, unauthenticated catalog.
        public = await publisher_client.get(f"/api/v1/marketplace/listings/{listing['slug']}")
        assert public.status_code == 200
        await db_session.rollback()

    async def test_an_approval_is_audit_logged_with_the_acting_admin(
        self,
        db_session: AsyncSession,
        make_client: Callable[[str], AsyncClient],
        unique_name: str,
    ) -> None:
        # Logged on success, not only on denial: putting a listing in
        # front of every customer is exactly the change an incident
        # review needs to attribute.
        publisher_user = f"publisher-{unique_name}"
        admin = f"admin-{unique_name}"
        await _make_user(db_session, publisher_user)
        await _make_user(db_session, admin)
        await _make_platform_admin(db_session, admin)

        publisher_client = make_client(publisher_user)
        workspace = await _workspace(publisher_client, f"ws-{unique_name}")
        listing = await _submitted_listing(publisher_client, workspace)
        await make_client(admin).post(
            f"/api/v1/admin/marketplace/listings/{listing['id']}/approve", json={}
        )

        result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "marketplace.listing_approved",
                AuditLog.target == listing["id"],
            )
        )
        entry = result.scalars().first()
        assert entry is not None
        assert entry.actor_user_id == admin
        await db_session.rollback()

    async def test_a_rejection_without_a_reason_is_refused(
        self,
        db_session: AsyncSession,
        make_client: Callable[[str], AsyncClient],
        unique_name: str,
    ) -> None:
        # A publisher told "rejected" with no reason cannot fix anything,
        # and will resubmit the same listing.
        publisher_user = f"publisher-{unique_name}"
        admin = f"admin-{unique_name}"
        await _make_user(db_session, publisher_user)
        await _make_user(db_session, admin)
        await _make_platform_admin(db_session, admin)

        publisher_client = make_client(publisher_user)
        workspace = await _workspace(publisher_client, f"ws-{unique_name}")
        listing = await _submitted_listing(publisher_client, workspace)

        response = await make_client(admin).post(
            f"/api/v1/admin/marketplace/listings/{listing['id']}/reject",
            json={"note": "   "},
        )

        assert response.status_code == 422
        await db_session.rollback()

    async def test_a_rejection_with_a_reason_reaches_the_publisher(
        self,
        db_session: AsyncSession,
        make_client: Callable[[str], AsyncClient],
        unique_name: str,
    ) -> None:
        publisher_user = f"publisher-{unique_name}"
        admin = f"admin-{unique_name}"
        await _make_user(db_session, publisher_user)
        await _make_user(db_session, admin)
        await _make_platform_admin(db_session, admin)

        publisher_client = make_client(publisher_user)
        workspace = await _workspace(publisher_client, f"ws-{unique_name}")
        listing = await _submitted_listing(publisher_client, workspace)

        rejected = await make_client(admin).post(
            f"/api/v1/admin/marketplace/listings/{listing['id']}/reject",
            json={"note": "The description does not say what it does."},
        )

        assert rejected.status_code == 200
        assert rejected.json()["status"] == "rejected"

        # The publisher can still see it — and fix and resubmit it,
        # keeping its reviews and history.
        mine = await publisher_client.get(f"/api/v1/workspaces/{workspace}/marketplace/listings")
        assert mine.status_code == 200
        assert any(row["slug"] == listing["slug"] for row in mine.json())
        await db_session.rollback()

    async def test_approving_something_not_awaiting_review_is_a_conflict(
        self,
        db_session: AsyncSession,
        make_client: Callable[[str], AsyncClient],
        unique_name: str,
    ) -> None:
        publisher_user = f"publisher-{unique_name}"
        admin = f"admin-{unique_name}"
        await _make_user(db_session, publisher_user)
        await _make_user(db_session, admin)
        await _make_platform_admin(db_session, admin)

        publisher_client = make_client(publisher_user)
        admin_client = make_client(admin)
        workspace = await _workspace(publisher_client, f"ws-{unique_name}")
        listing = await _submitted_listing(publisher_client, workspace)
        await admin_client.post(
            f"/api/v1/admin/marketplace/listings/{listing['id']}/approve", json={}
        )

        again = await admin_client.post(
            f"/api/v1/admin/marketplace/listings/{listing['id']}/approve", json={}
        )

        assert again.status_code == 409
        await db_session.rollback()

    async def test_featuring_is_a_platform_decision_not_a_publishers(
        self,
        db_session: AsyncSession,
        make_client: Callable[[str], AsyncClient],
        unique_name: str,
    ) -> None:
        # Otherwise every publisher features themselves and the rail
        # means nothing.
        publisher_user = f"publisher-{unique_name}"
        admin = f"admin-{unique_name}"
        await _make_user(db_session, publisher_user)
        await _make_user(db_session, admin)
        await _make_platform_admin(db_session, admin)

        publisher_client = make_client(publisher_user)
        workspace = await _workspace(publisher_client, f"ws-{unique_name}")
        listing = await _submitted_listing(publisher_client, workspace)

        refused = await publisher_client.post(
            f"/api/v1/admin/marketplace/listings/{listing['id']}/feature",
            json={"is_featured": True},
        )
        assert refused.status_code == 404

        allowed = await make_client(admin).post(
            f"/api/v1/admin/marketplace/listings/{listing['id']}/feature",
            json={"is_featured": True},
        )
        assert allowed.status_code == 200
        assert allowed.json()["is_featured"] is True
        await db_session.rollback()


class TestInstallRoutes:
    async def test_installing_returns_201_then_200_on_a_repeat(
        self,
        db_session: AsyncSession,
        make_client: Callable[[str], AsyncClient],
        unique_name: str,
    ) -> None:
        # 200 on the retry so a caller can see it did not create a
        # second agent.
        publisher_user = f"publisher-{unique_name}"
        installer_user = f"installer-{unique_name}"
        admin = f"admin-{unique_name}"
        for user in (publisher_user, installer_user, admin):
            await _make_user(db_session, user)
        await _make_platform_admin(db_session, admin)

        publisher_client = make_client(publisher_user)
        publisher_workspace = await _workspace(publisher_client, f"pub-{unique_name}")
        listing = await _submitted_listing(publisher_client, publisher_workspace)
        await make_client(admin).post(
            f"/api/v1/admin/marketplace/listings/{listing['id']}/approve", json={}
        )

        installer_client = make_client(installer_user)
        installer_workspace = await _workspace(installer_client, f"inst-{unique_name}")
        path = (
            f"/api/v1/workspaces/{installer_workspace}"
            f"/marketplace/listings/{listing['slug']}/install"
        )

        first = await installer_client.post(path, json={})
        assert first.status_code == 201, first.text
        assert first.json()["created"] is True

        second = await installer_client.post(path, json={})
        assert second.status_code == 200
        assert second.json()["created"] is False
        assert second.json()["agent_id"] == first.json()["agent_id"]
        await db_session.rollback()

    async def test_a_stranger_cannot_install_into_another_workspace(
        self,
        db_session: AsyncSession,
        make_client: Callable[[str], AsyncClient],
        unique_name: str,
    ) -> None:
        # `workspace_id` comes from the authenticated context; a path
        # naming someone else's workspace must not resolve.
        owner = f"owner-{unique_name}"
        stranger = f"stranger-{unique_name}"
        admin = f"admin-{unique_name}"
        for user in (owner, stranger, admin):
            await _make_user(db_session, user)
        await _make_platform_admin(db_session, admin)

        owner_client = make_client(owner)
        owner_workspace = await _workspace(owner_client, f"ws-{unique_name}")
        listing = await _submitted_listing(owner_client, owner_workspace)
        await make_client(admin).post(
            f"/api/v1/admin/marketplace/listings/{listing['id']}/approve", json={}
        )

        response = await make_client(stranger).post(
            f"/api/v1/workspaces/{owner_workspace}/marketplace/listings/{listing['slug']}/install",
            json={},
        )

        assert response.status_code == 404
        await db_session.rollback()

    async def test_an_unpublished_listing_cannot_be_installed_over_http(
        self,
        db_session: AsyncSession,
        make_client: Callable[[str], AsyncClient],
        unique_name: str,
    ) -> None:
        publisher_user = f"publisher-{unique_name}"
        await _make_user(db_session, publisher_user)
        client = make_client(publisher_user)
        workspace = await _workspace(client, f"ws-{unique_name}")
        listing = await _submitted_listing(client, workspace)

        response = await client.post(
            f"/api/v1/workspaces/{workspace}/marketplace/listings/{listing['slug']}/install",
            json={},
        )

        assert response.status_code == 409
        await db_session.rollback()

    async def test_the_installs_list_is_scoped_to_the_calling_workspace(
        self,
        db_session: AsyncSession,
        make_client: Callable[[str], AsyncClient],
        unique_name: str,
    ) -> None:
        publisher_user = f"publisher-{unique_name}"
        installer_user = f"installer-{unique_name}"
        admin = f"admin-{unique_name}"
        for user in (publisher_user, installer_user, admin):
            await _make_user(db_session, user)
        await _make_platform_admin(db_session, admin)

        publisher_client = make_client(publisher_user)
        publisher_workspace = await _workspace(publisher_client, f"pub-{unique_name}")
        listing = await _submitted_listing(publisher_client, publisher_workspace)
        await make_client(admin).post(
            f"/api/v1/admin/marketplace/listings/{listing['id']}/approve", json={}
        )

        installer_client = make_client(installer_user)
        installer_workspace = await _workspace(installer_client, f"inst-{unique_name}")
        await installer_client.post(
            f"/api/v1/workspaces/{installer_workspace}"
            f"/marketplace/listings/{listing['slug']}/install",
            json={},
        )

        mine = await installer_client.get(
            f"/api/v1/workspaces/{installer_workspace}/marketplace/installs"
        )
        assert mine.status_code == 200
        assert len(mine.json()) == 1
        assert mine.json()[0]["upgrade_available"] is False

        # The publisher installed nothing, and sees nothing.
        theirs = await publisher_client.get(
            f"/api/v1/workspaces/{publisher_workspace}/marketplace/installs"
        )
        assert theirs.status_code == 200
        assert theirs.json() == []
        await db_session.rollback()
