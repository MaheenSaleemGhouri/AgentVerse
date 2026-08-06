"""The seeded template library, against the real database.

The library only exists as migration output, so a unit test over
`TEMPLATES` proves the source list is sane and nothing more. These check
that the rows actually landed, are reachable through the same public
catalog customers use, and install like any other listing — which is the
whole claim behind not building a parallel templates system.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.marketplace_service.application.install_service import InstallService
from agentverse_api.marketplace_service.application.marketplace_service import (
    MarketplaceService,
)
from agentverse_api.marketplace_service.domain.listing import ListingStatus, Pricing
from agentverse_api.marketplace_service.domain.templates import (
    PLATFORM_WORKSPACE_ID,
    PLATFORM_WORKSPACE_SLUG,
    TEMPLATES,
)
from agentverse_api.marketplace_service.infrastructure.agent_importer import (
    OrchestrationAgentImporter,
)
from agentverse_api.marketplace_service.infrastructure.repositories import (
    SqlCategoryRepository,
    SqlInstallRepository,
    SqlListingRepository,
    SqlListingVersionRepository,
    SqlReviewRepository,
)
from agentverse_api.orchestration_service.infrastructure.repositories import SqlAgentRepository

pytestmark = pytest.mark.integration


def _marketplace(session: AsyncSession) -> MarketplaceService:
    return MarketplaceService(
        listings=SqlListingRepository(session),
        versions=SqlListingVersionRepository(session),
        reviews=SqlReviewRepository(session),
        categories=SqlCategoryRepository(session),
    )


def _installs(session: AsyncSession) -> InstallService:
    return InstallService(
        listings=SqlListingRepository(session),
        versions=SqlListingVersionRepository(session),
        installs=SqlInstallRepository(session),
        agents=OrchestrationAgentImporter(SqlAgentRepository(session)),
    )


async def _workspace(session: AsyncSession) -> str:
    workspace_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO workspaces (id, name, slug, created_at) "
            "VALUES (:id, 'Template Test', :slug, now())"
        ),
        {"id": workspace_id, "slug": f"ws-{workspace_id[:8]}"},
    )
    await session.flush()
    return workspace_id


async def _user(session: AsyncSession) -> str:
    user_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO users (id, name, email, email_verified, created_at, updated_at) "
            "VALUES (:id, 'Installer', :email, true, now(), now())"
        ),
        {"id": user_id, "email": f"{user_id[:8]}@example.test"},
    )
    await session.flush()
    return user_id


class TestTheSeed:
    async def test_every_template_landed(self, db_session: AsyncSession) -> None:
        listings, total = await _marketplace(db_session).browse(official_only=True, limit=100)
        assert total == len(TEMPLATES)
        assert {listing.slug for listing in listings} == {t.slug for t in TEMPLATES}
        await db_session.rollback()

    async def test_every_template_is_published_and_free(self, db_session: AsyncSession) -> None:
        # A first-party template that charged would make "official" mean
        # something other than "we wrote this".
        listings, _ = await _marketplace(db_session).browse(official_only=True, limit=100)
        for listing in listings:
            assert listing.status is ListingStatus.PUBLISHED, listing.slug
            assert listing.pricing is Pricing.FREE, listing.slug
            assert listing.price_cents == 0, listing.slug
        await db_session.rollback()

    async def test_every_template_has_a_version_to_install(self, db_session: AsyncSession) -> None:
        # `latest_version` pointing at a version that does not exist
        # would make install fail for everyone, on the front page.
        service = _marketplace(db_session)
        for template in TEMPLATES:
            versions = await service.versions_of(slug=template.slug, viewer_workspace_id=None)
            assert len(versions) == 1, template.slug
            assert versions[0].version_number == 1

    async def test_the_stored_config_matches_the_source(self, db_session: AsyncSession) -> None:
        # The seed and `domain/templates.py` drifting would mean the
        # library says one thing and installs another.
        service = _marketplace(db_session)
        for template in TEMPLATES:
            versions = await service.versions_of(slug=template.slug, viewer_workspace_id=None)
            assert versions[0].config == template.to_config(), template.slug

    async def test_the_platform_workspace_has_no_members(self, db_session: AsyncSession) -> None:
        # Curation by construction: nobody can authenticate into it, so
        # the publisher routes are unreachable and a template can only
        # change through a reviewed migration.
        result = await db_session.execute(
            text("SELECT count(*) FROM workspace_members WHERE workspace_id = :ws"),
            {"ws": PLATFORM_WORKSPACE_ID},
        )
        assert result.scalar_one() == 0

    async def test_the_platform_workspace_is_the_publisher(self, db_session: AsyncSession) -> None:
        listings, _ = await _marketplace(db_session).browse(official_only=True, limit=100)
        assert {listing.publisher_workspace_id for listing in listings} == {PLATFORM_WORKSPACE_ID}
        result = await db_session.execute(
            text("SELECT slug FROM workspaces WHERE id = :ws"),
            {"ws": PLATFORM_WORKSPACE_ID},
        )
        assert result.scalar_one() == PLATFORM_WORKSPACE_SLUG


class TestTheCatalogFilter:
    async def test_official_true_returns_only_templates(self, db_session: AsyncSession) -> None:
        listings, _ = await _marketplace(db_session).browse(official_only=True, limit=100)
        assert all(listing.is_official for listing in listings)
        await db_session.rollback()

    async def test_official_false_excludes_templates(self, db_session: AsyncSession) -> None:
        listings, _ = await _marketplace(db_session).browse(official_only=False, limit=100)
        assert not any(listing.is_official for listing in listings)
        await db_session.rollback()

    async def test_omitting_the_filter_returns_the_whole_catalog(
        self, db_session: AsyncSession
    ) -> None:
        # The tri-state's reason for existing: a plain bool could not
        # express "everything", which is what a catalog page wants.
        _, total_all = await _marketplace(db_session).browse(limit=100)
        _, total_official = await _marketplace(db_session).browse(official_only=True, limit=100)
        assert total_all >= total_official
        await db_session.rollback()

    async def test_a_template_is_reachable_anonymously_like_any_listing(
        self, db_session: AsyncSession
    ) -> None:
        listing = await _marketplace(db_session).get(
            slug="research-assistant", viewer_workspace_id=None
        )
        assert listing.is_official is True
        assert listing.status is ListingStatus.PUBLISHED

    async def test_templates_can_be_filtered_by_category(self, db_session: AsyncSession) -> None:
        listings, _ = await _marketplace(db_session).browse(
            official_only=True, category_slug="engineering", limit=100
        )
        assert {listing.slug for listing in listings} == {"code-reviewer"}
        await db_session.rollback()


class TestInstallingATemplate:
    async def test_a_template_installs_like_any_other_listing(
        self, db_session: AsyncSession
    ) -> None:
        # The claim behind not building a parallel templates system: one
        # install path serves both.
        workspace = await _workspace(db_session)
        user = await _user(db_session)

        result = await _installs(db_session).install(
            slug="research-assistant", workspace_id=workspace, installed_by_user_id=user
        )

        assert result.created is True
        agent = await SqlAgentRepository(db_session).get_agent(
            workspace_id=workspace, agent_id=result.agent_id
        )
        assert agent is not None
        assert agent.name == "Research Assistant"
        await db_session.rollback()

    async def test_the_installed_agent_carries_the_templates_prompt(
        self, db_session: AsyncSession
    ) -> None:
        workspace = await _workspace(db_session)
        user = await _user(db_session)
        template = next(t for t in TEMPLATES if t.slug == "code-reviewer")

        result = await _installs(db_session).install(
            slug=template.slug, workspace_id=workspace, installed_by_user_id=user
        )

        version = await SqlAgentRepository(db_session).get_latest_version(agent_id=result.agent_id)
        assert version is not None
        assert version.config.system_instructions == template.system_instructions
        assert version.config.model == template.model
        await db_session.rollback()

    async def test_every_template_installs(self, db_session: AsyncSession) -> None:
        # Twelve installs is cheap, and "one of the twelve is broken" is
        # exactly the failure a spot check misses.
        workspace = await _workspace(db_session)
        user = await _user(db_session)
        service = _installs(db_session)

        for template in TEMPLATES:
            result = await service.install(
                slug=template.slug, workspace_id=workspace, installed_by_user_id=user
            )
            assert result.created is True, template.slug

        installs = await service.list_installs(workspace_id=workspace, limit=100)
        assert len(installs) == len(TEMPLATES)
        await db_session.rollback()

    async def test_installing_a_template_twice_returns_the_same_agent(
        self, db_session: AsyncSession
    ) -> None:
        workspace = await _workspace(db_session)
        user = await _user(db_session)
        service = _installs(db_session)

        first = await service.install(
            slug="meeting-notes", workspace_id=workspace, installed_by_user_id=user
        )
        second = await service.install(
            slug="meeting-notes", workspace_id=workspace, installed_by_user_id=user
        )

        assert second.agent_id == first.agent_id
        assert second.created is False
        await db_session.rollback()

    async def test_a_template_can_be_installed_under_a_chosen_name(
        self, db_session: AsyncSession
    ) -> None:
        workspace = await _workspace(db_session)
        user = await _user(db_session)

        result = await _installs(db_session).install(
            slug="email-drafter",
            workspace_id=workspace,
            installed_by_user_id=user,
            name="Support replies",
        )

        agent = await SqlAgentRepository(db_session).get_agent(
            workspace_id=workspace, agent_id=result.agent_id
        )
        assert agent is not None
        assert agent.name == "Support replies"
        await db_session.rollback()
