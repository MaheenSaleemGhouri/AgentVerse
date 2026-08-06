"""Installing a listing, against real Postgres and a real agent write.

The install path crosses a context boundary — a marketplace listing
becomes an `agents`/`agent_versions` row owned by orchestration — so
these run against the real schema on both sides rather than a fake.

What is being pinned down:

- the copy really lands in the *installing* workspace, not the
  publisher's;
- a repeat install returns the same agent instead of a second one, and
  the unique index makes that true under concurrency rather than by
  convention;
- the install count moves once per genuinely new install, and can be
  reconciled against real rows.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.marketplace_service.application.install_service import (
    InstallService,
    ListingNotInstallableError,
    ModerationService,
    NoSuchVersionError,
)
from agentverse_api.marketplace_service.application.marketplace_service import (
    MarketplaceService,
)
from agentverse_api.marketplace_service.domain.install import UninstallableConfigError
from agentverse_api.marketplace_service.domain.listing import ListingKind, ListingStatus, Pricing
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

_SUMMARY = "A genuinely useful research agent for teams that need citations."
_DESCRIPTION = "x" * 200
_CONFIG: dict[str, object] = {
    "model": "gpt-4o-mini",
    "system_instructions": "Research things and cite sources.",
    "temperature": 0.3,
    "tools": ["web_search"],
}


async def _workspace(session: AsyncSession) -> str:
    workspace_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO workspaces (id, name, slug, created_at) VALUES (:id, :name, :slug, now())"
        ),
        {"id": workspace_id, "name": "Install Test", "slug": f"ws-{workspace_id[:8]}"},
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


async def _publish(
    session: AsyncSession,
    publisher: str,
    *,
    config: dict[str, object] | None = None,
    approve: bool = True,
) -> str:
    """A listing carried through moderation, ready to install."""
    service = _marketplace(session)
    listing = await service.create_listing(
        publisher_workspace_id=publisher,
        publisher_name="Acme",
        kind=ListingKind.AGENT,
        title=f"Installable {uuid.uuid4().hex[:8]}",
        summary=_SUMMARY,
        description=_DESCRIPTION,
        category_slug="research",
        pricing=Pricing.FREE,
        price_cents=0,
    )
    await service.publish_version(
        slug=listing.slug,
        actor_workspace_id=publisher,
        config=config if config is not None else dict(_CONFIG),
        changelog="Initial release",
    )
    await service.submit_for_review(slug=listing.slug, actor_workspace_id=publisher)
    if approve:
        await service.approve(listing_id=listing.id)
    return listing.slug


async def _agent_workspace(session: AsyncSession, agent_id: str) -> str:
    result = await session.execute(
        text("SELECT workspace_id FROM agents WHERE id = :id"), {"id": agent_id}
    )
    return str(result.scalar_one())


class TestInstall:
    async def test_installing_creates_an_agent_in_the_installers_workspace(
        self, db_session: AsyncSession
    ) -> None:
        # The whole point, and the thing that would be a tenancy bug if
        # it landed in the publisher's workspace instead.
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)

        result = await _installs(db_session).install(
            slug=slug, workspace_id=installer, installed_by_user_id=user
        )

        assert result.created is True
        assert await _agent_workspace(db_session, result.agent_id) == installer
        await db_session.rollback()

    async def test_the_installed_agent_carries_the_snapshot_config(
        self, db_session: AsyncSession
    ) -> None:
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)

        result = await _installs(db_session).install(
            slug=slug, workspace_id=installer, installed_by_user_id=user
        )

        version = await SqlAgentRepository(db_session).get_latest_version(agent_id=result.agent_id)
        assert version is not None
        assert version.config.model == "gpt-4o-mini"
        assert version.config.tools == ["web_search"]
        await db_session.rollback()

    async def test_the_publishers_knowledge_bases_do_not_cross_into_the_install(
        self, db_session: AsyncSession
    ) -> None:
        # End-to-end version of the domain test: those ids name knowledge
        # bases in the publisher's workspace, and an agent in someone
        # else's holding them is a cross-tenant reference.
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(
            db_session,
            publisher,
            config={**_CONFIG, "knowledge_base_ids": [str(uuid.uuid4())]},
        )

        result = await _installs(db_session).install(
            slug=slug, workspace_id=installer, installed_by_user_id=user
        )

        version = await SqlAgentRepository(db_session).get_latest_version(agent_id=result.agent_id)
        assert version is not None
        assert version.config.knowledge_base_ids == []
        await db_session.rollback()

    async def test_a_broken_snapshot_is_refused_with_its_reasons(
        self, db_session: AsyncSession
    ) -> None:
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher, config={"system_instructions": "no model"})

        with pytest.raises(UninstallableConfigError) as exc:
            await _installs(db_session).install(
                slug=slug, workspace_id=installer, installed_by_user_id=user
            )
        assert any("names no model" in problem for problem in exc.value.problems)
        await db_session.rollback()

    async def test_the_agent_is_named_after_the_listing_by_default(
        self, db_session: AsyncSession
    ) -> None:
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)
        listing = await _marketplace(db_session).get(slug=slug, viewer_workspace_id=None)

        result = await _installs(db_session).install(
            slug=slug, workspace_id=installer, installed_by_user_id=user
        )

        agent = await SqlAgentRepository(db_session).get_agent(
            workspace_id=installer, agent_id=result.agent_id
        )
        assert agent is not None
        assert agent.name == listing.title
        await db_session.rollback()

    async def test_an_explicit_name_wins(self, db_session: AsyncSession) -> None:
        # A workspace installing two variants needs to tell them apart.
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)

        result = await _installs(db_session).install(
            slug=slug,
            workspace_id=installer,
            installed_by_user_id=user,
            name="Our research agent",
        )

        agent = await SqlAgentRepository(db_session).get_agent(
            workspace_id=installer, agent_id=result.agent_id
        )
        assert agent is not None
        assert agent.name == "Our research agent"
        await db_session.rollback()


class TestWhatCannotBeInstalled:
    async def test_an_unpublished_listing_cannot_be_installed_even_by_its_publisher(
        self, db_session: AsyncSession
    ) -> None:
        # "It is mine" is not the same as "it has been reviewed" — and
        # allowing it would make moderation optional for anyone willing
        # to install their own draft.
        publisher = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher, approve=False)

        with pytest.raises(ListingNotInstallableError):
            await _installs(db_session).install(
                slug=slug, workspace_id=publisher, installed_by_user_id=user
            )
        await db_session.rollback()

    async def test_an_unlisted_listing_cannot_be_installed_afresh(
        self, db_session: AsyncSession
    ) -> None:
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)
        await _marketplace(db_session).unlist(slug=slug, actor_workspace_id=publisher)

        with pytest.raises(ListingNotInstallableError):
            await _installs(db_session).install(
                slug=slug, workspace_id=installer, installed_by_user_id=user
            )
        await db_session.rollback()

    async def test_an_unknown_slug_is_not_found(self, db_session: AsyncSession) -> None:
        installer = await _workspace(db_session)
        user = await _user(db_session)
        with pytest.raises(NoSuchVersionError):
            await _installs(db_session).install(
                slug="no-such-listing", workspace_id=installer, installed_by_user_id=user
            )
        await db_session.rollback()

    async def test_a_version_that_does_not_exist_is_not_found(
        self, db_session: AsyncSession
    ) -> None:
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)

        with pytest.raises(NoSuchVersionError):
            await _installs(db_session).install(
                slug=slug,
                workspace_id=installer,
                installed_by_user_id=user,
                version_number=99,
            )
        await db_session.rollback()


class TestRepeatInstalls:
    async def test_a_second_install_returns_the_same_agent(self, db_session: AsyncSession) -> None:
        # A double-clicked install must not leave two agents behind.
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)
        service = _installs(db_session)

        first = await service.install(slug=slug, workspace_id=installer, installed_by_user_id=user)
        second = await service.install(slug=slug, workspace_id=installer, installed_by_user_id=user)

        assert second.agent_id == first.agent_id
        assert second.created is False
        await db_session.rollback()

    async def test_one_install_row_per_workspace_listing_and_version(
        self, db_session: AsyncSession
    ) -> None:
        # Enforced by a unique index rather than the check above, because
        # two concurrent installs would both pass a check and the loser
        # would fail *after* having already created an agent.
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)
        await _installs(db_session).install(
            slug=slug, workspace_id=installer, installed_by_user_id=user
        )
        listing = await _marketplace(db_session).get(slug=slug, viewer_workspace_id=None)

        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO marketplace_installs "
                    "(id, workspace_id, listing_id, version_number, installed_by_user_id) "
                    "VALUES (gen_random_uuid(), :ws, :lid, 1, :uid)"
                ),
                {"ws": installer, "lid": listing.id, "uid": user},
            )
        await db_session.rollback()

    async def test_installing_a_newer_version_records_separately(
        self, db_session: AsyncSession
    ) -> None:
        # The difference between a retry and an upgrade.
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)
        await _installs(db_session).install(
            slug=slug, workspace_id=installer, installed_by_user_id=user
        )
        await _marketplace(db_session).publish_version(
            slug=slug,
            actor_workspace_id=publisher,
            config={**_CONFIG, "model": "gpt-4o"},
            changelog="Better model",
        )

        upgraded = await _installs(db_session).install(
            slug=slug, workspace_id=installer, installed_by_user_id=user
        )

        assert upgraded.created is True
        assert upgraded.install.version_number == 2
        installs = await _installs(db_session).list_installs(workspace_id=installer)
        assert sorted(i.version_number for i in installs) == [1, 2]
        await db_session.rollback()

    async def test_reinstalling_after_deleting_the_copy_creates_a_fresh_agent(
        self, db_session: AsyncSession
    ) -> None:
        # A record pointing at an agent the installer deleted should
        # install again, not hand back a dead id.
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)
        service = _installs(db_session)
        first = await service.install(slug=slug, workspace_id=installer, installed_by_user_id=user)
        await SqlAgentRepository(db_session).soft_delete(
            workspace_id=installer, agent_id=first.agent_id
        )

        second = await service.install(slug=slug, workspace_id=installer, installed_by_user_id=user)

        assert second.agent_id != first.agent_id
        assert second.created is True
        await db_session.rollback()


class TestInstallCount:
    async def test_a_new_install_moves_the_catalog_counter(self, db_session: AsyncSession) -> None:
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)

        await _installs(db_session).install(
            slug=slug, workspace_id=installer, installed_by_user_id=user
        )

        listing = await _marketplace(db_session).get(slug=slug, viewer_workspace_id=None)
        assert listing.install_count == 1
        await db_session.rollback()

    async def test_a_repeat_install_does_not_move_the_counter(
        self, db_session: AsyncSession
    ) -> None:
        # Otherwise anyone could inflate a listing's popularity — the
        # number the catalog sorts by — in a loop.
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)
        service = _installs(db_session)

        for _ in range(4):
            await service.install(slug=slug, workspace_id=installer, installed_by_user_id=user)

        listing = await _marketplace(db_session).get(slug=slug, viewer_workspace_id=None)
        assert listing.install_count == 1
        await db_session.rollback()

    async def test_two_workspaces_installing_count_twice(self, db_session: AsyncSession) -> None:
        publisher = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)
        service = _installs(db_session)
        for _ in range(2):
            await service.install(
                slug=slug,
                workspace_id=await _workspace(db_session),
                installed_by_user_id=user,
            )

        listing = await _marketplace(db_session).get(slug=slug, viewer_workspace_id=None)
        assert listing.install_count == 2
        await db_session.rollback()

    async def test_the_counter_agrees_with_the_install_rows(self, db_session: AsyncSession) -> None:
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)
        service = _installs(db_session)
        await service.install(slug=slug, workspace_id=installer, installed_by_user_id=user)
        listing = await _marketplace(db_session).get(slug=slug, viewer_workspace_id=None)

        assert await service.reconcile_install_count(listing.id) is None
        await db_session.rollback()

    async def test_reconciliation_reports_a_counter_written_from_outside(
        self, db_session: AsyncSession
    ) -> None:
        # Reports rather than repairs: a disagreement means something
        # wrote the denormalized column outside the transaction that owns
        # it, which is worth a human looking at.
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)
        service = _installs(db_session)
        await service.install(slug=slug, workspace_id=installer, installed_by_user_id=user)
        listing = await _marketplace(db_session).get(slug=slug, viewer_workspace_id=None)

        await db_session.execute(
            text("UPDATE marketplace_listings SET install_count = 99 WHERE id = :id"),
            {"id": listing.id},
        )

        assert await service.reconcile_install_count(listing.id) == 1
        await db_session.rollback()


class TestUpgradeVisibility:
    async def test_an_install_shows_an_upgrade_once_the_publisher_moves_on(
        self, db_session: AsyncSession
    ) -> None:
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)
        service = _installs(db_session)
        await service.install(slug=slug, workspace_id=installer, installed_by_user_id=user)

        installs = await service.list_installs(workspace_id=installer)
        resolved = await service.upgrade_available(install=installs[0])
        assert resolved is not None
        assert resolved[1] is False

        await _marketplace(db_session).publish_version(
            slug=slug, actor_workspace_id=publisher, config=dict(_CONFIG), changelog="v2"
        )
        resolved = await service.upgrade_available(install=installs[0])
        assert resolved is not None
        assert resolved[1] is True
        await db_session.rollback()

    async def test_a_withdrawn_listing_offers_nothing(self, db_session: AsyncSession) -> None:
        # The installed agent is unaffected either way — it is a copy.
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)
        service = _installs(db_session)
        await service.install(slug=slug, workspace_id=installer, installed_by_user_id=user)
        await _marketplace(db_session).unlist(slug=slug, actor_workspace_id=publisher)

        installs = await service.list_installs(workspace_id=installer)
        assert await service.upgrade_available(install=installs[0]) is None
        await db_session.rollback()

    async def test_install_history_is_scoped_to_its_workspace(
        self, db_session: AsyncSession
    ) -> None:
        # The catalog's public-read exception stops at the catalog.
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        stranger = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)
        service = _installs(db_session)
        await service.install(slug=slug, workspace_id=installer, installed_by_user_id=user)

        assert await service.list_installs(workspace_id=stranger) == []
        assert len(await service.list_installs(workspace_id=installer)) == 1
        await db_session.rollback()


class TestDatabaseInvariants:
    async def test_a_workspace_with_installs_can_still_be_deleted(
        self, db_session: AsyncSession
    ) -> None:
        # CASCADE, unlike the listing's own workspace FK: an install is
        # the installer's own record, and deleting their workspace should
        # not be blocked by it.
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)
        await _installs(db_session).install(
            slug=slug, workspace_id=installer, installed_by_user_id=user
        )
        await db_session.flush()

        await db_session.execute(
            text("DELETE FROM agents WHERE workspace_id = :ws"), {"ws": installer}
        )
        await db_session.execute(text("DELETE FROM workspaces WHERE id = :ws"), {"ws": installer})
        remaining = await db_session.execute(
            text("SELECT count(*) FROM marketplace_installs WHERE workspace_id = :ws"),
            {"ws": installer},
        )
        assert remaining.scalar_one() == 0
        await db_session.rollback()

    async def test_a_listing_with_installs_cannot_be_deleted(
        self, db_session: AsyncSession
    ) -> None:
        # RESTRICT: the listing row is what makes an install explicable.
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)
        await _installs(db_session).install(
            slug=slug, workspace_id=installer, installed_by_user_id=user
        )
        listing = await _marketplace(db_session).get(slug=slug, viewer_workspace_id=None)
        await db_session.flush()

        with pytest.raises(IntegrityError):
            await db_session.execute(
                text("DELETE FROM marketplace_listings WHERE id = :id"), {"id": listing.id}
            )
        await db_session.rollback()

    async def test_a_version_number_below_one_is_rejected(self, db_session: AsyncSession) -> None:
        publisher = await _workspace(db_session)
        installer = await _workspace(db_session)
        user = await _user(db_session)
        slug = await _publish(db_session, publisher)
        listing = await _marketplace(db_session).get(slug=slug, viewer_workspace_id=None)

        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO marketplace_installs "
                    "(id, workspace_id, listing_id, version_number, installed_by_user_id) "
                    "VALUES (gen_random_uuid(), :ws, :lid, 0, :uid)"
                ),
                {"ws": installer, "lid": listing.id, "uid": user},
            )
        await db_session.rollback()


class TestModerationQueue:
    async def test_the_queue_holds_only_submissions_awaiting_a_decision(
        self, db_session: AsyncSession
    ) -> None:
        publisher = await _workspace(db_session)
        await _publish(db_session, publisher, approve=False)
        approved_slug = await _publish(db_session, publisher)

        queue = await ModerationService(listings=SqlListingRepository(db_session)).queue()

        assert all(listing.status is ListingStatus.PENDING_REVIEW for listing in queue)
        assert approved_slug not in {listing.slug for listing in queue}
        await db_session.rollback()

    async def test_the_queue_is_oldest_first(self, db_session: AsyncSession) -> None:
        # Newest-first starves the tail: the listing nobody looked at
        # yesterday is the one most in need of looking at today.
        publisher = await _workspace(db_session)
        for _ in range(3):
            await _publish(db_session, publisher, approve=False)

        queue = await ModerationService(listings=SqlListingRepository(db_session)).queue()

        assert [listing.updated_at for listing in queue] == sorted(
            listing.updated_at for listing in queue
        )
        await db_session.rollback()

    async def test_the_queue_spans_every_workspace(self, db_session: AsyncSession) -> None:
        # It is a platform-staff view, and moderating only your own
        # workspace's submissions would be nothing at all.
        first = await _workspace(db_session)
        second = await _workspace(db_session)
        await _publish(db_session, first, approve=False)
        await _publish(db_session, second, approve=False)

        queue = await ModerationService(listings=SqlListingRepository(db_session)).queue()

        publishers = {listing.publisher_workspace_id for listing in queue}
        assert {first, second} <= publishers
        await db_session.rollback()

    async def test_approving_moves_the_listing_into_the_public_catalog(
        self, db_session: AsyncSession
    ) -> None:
        publisher = await _workspace(db_session)
        slug = await _publish(db_session, publisher, approve=False)
        service = _marketplace(db_session)
        listing = await service.get(slug=slug, viewer_workspace_id=publisher)

        await service.approve(listing_id=listing.id)

        assert (
            await service.get(slug=slug, viewer_workspace_id=None)
        ).status is ListingStatus.PUBLISHED
        await db_session.rollback()

    async def test_a_rejected_listing_leaves_the_queue_and_keeps_its_note(
        self, db_session: AsyncSession
    ) -> None:
        publisher = await _workspace(db_session)
        slug = await _publish(db_session, publisher, approve=False)
        service = _marketplace(db_session)
        listing = await service.get(slug=slug, viewer_workspace_id=publisher)

        await service.reject(listing_id=listing.id, note="The description says nothing.")

        queue = await ModerationService(listings=SqlListingRepository(db_session)).queue()
        assert slug not in {entry.slug for entry in queue}
        note = await db_session.execute(
            text("SELECT moderation_note FROM marketplace_listings WHERE id = :id"),
            {"id": listing.id},
        )
        assert note.scalar_one() == "The description says nothing."
        await db_session.rollback()
