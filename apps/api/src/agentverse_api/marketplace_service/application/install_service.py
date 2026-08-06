"""Installing a listing, and moderating the catalog.

Two use cases that share nothing but a repository set, kept in one module
because splitting them would mean two composition roots over the same
four dependencies.

**Install copies; it never links.** A published version's config is
snapshotted into a brand-new agent in the installing workspace. From that
moment the two are unrelated: the publisher can unlist, rewrite or delete
their source and the installed agent keeps working. That is the property
that makes a marketplace trustworthy, and it is why nothing here stores a
runtime reference back to the listing.

**The snapshot is untrusted input.** It was authored in someone else's
workspace and is about to become an agent in the installer's, so it goes
through `domain.install.sanitize_config` — which drops the publisher's
`knowledge_base_ids` (a cross-tenant reference with nothing to remap to)
and caps the free text that reaches a model prompt.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_api.marketplace_service.domain.install import (
    MarketplaceInstall,
    is_upgrade,
    sanitize_config,
)
from agentverse_api.marketplace_service.domain.listing import (
    Listing,
    ListingStatus,
    is_public,
)
from agentverse_api.marketplace_service.domain.ports import (
    AgentImporter,
    InstallRepository,
    ListingRepository,
    ListingVersionRepository,
)


class ListingNotInstallableError(Exception):
    """The listing exists but cannot be installed right now. Maps to 409.

    Distinct from "no such listing": a publisher who unlists while
    someone is looking at the page should produce a message that says so,
    not a 404 for something the caller can plainly see.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class NoSuchVersionError(Exception):
    """Maps to HTTP 404."""

    def __init__(self, version_number: int | None) -> None:
        self.version_number = version_number
        super().__init__(
            "That version does not exist"
            if version_number is None
            else f"This listing has no version {version_number}"
        )


@dataclass(frozen=True, slots=True)
class InstallResult:
    install: MarketplaceInstall
    agent_id: str
    #: False when an identical install already existed and was returned
    #: unchanged. The route uses it to answer 200 rather than 201, so a
    #: retried request is visibly a retry.
    created: bool


@dataclass(slots=True)
class InstallService:
    listings: ListingRepository
    versions: ListingVersionRepository
    installs: InstallRepository
    agents: AgentImporter

    async def install(
        self,
        *,
        slug: str,
        workspace_id: str,
        installed_by_user_id: str,
        version_number: int | None = None,
        name: str | None = None,
    ) -> InstallResult:
        """Copy a published version into this workspace as a new agent.

        `version_number=None` installs the current version, which is what
        a one-click install means. Naming one explicitly exists so a
        workspace can pin, or re-install what they already reviewed.
        """
        listing = await self.listings.get_by_slug(slug)
        if listing is None:
            raise NoSuchVersionError(version_number)
        if not is_public(listing.status):
            # Only published listings install — including for the
            # publisher's own draft. A draft has not been moderated, and
            # "it is mine" is not the same as "it has been reviewed".
            raise ListingNotInstallableError(
                "This listing is not published, so there is nothing to install."
            )

        version = await self.versions.get_version(
            listing_id=listing.id, version_number=version_number
        )
        if version is None:
            raise NoSuchVersionError(version_number)

        existing = await self.installs.get(
            workspace_id=workspace_id,
            listing_id=listing.id,
            version_number=version.version_number,
        )
        # A retry, or a second click. Returning the same agent is the
        # honest answer — but only if it is still there: a record pointing
        # at an agent the installer has since deleted should install again
        # rather than hand back a dead id.
        if (
            existing is not None
            and existing.agent_id is not None
            and await self.agents.exists(workspace_id=workspace_id, agent_id=existing.agent_id)
        ):
            return InstallResult(install=existing, agent_id=existing.agent_id, created=False)

        config = sanitize_config(version.config)
        agent_id = await self.agents.create_from_listing(
            workspace_id=workspace_id,
            name=name or listing.title,
            description=listing.summary,
            created_by_user_id=installed_by_user_id,
            config=config,
        )
        install = await self.installs.record(
            workspace_id=workspace_id,
            listing_id=listing.id,
            version_number=version.version_number,
            agent_id=agent_id,
            installed_by_user_id=installed_by_user_id,
        )
        if existing is None:
            # Only a genuinely new install moves the counter. Re-installing
            # after deleting the copy is the same workspace installing the
            # same thing twice, and counting it would let anyone inflate a
            # listing's popularity in a loop.
            await self.listings.record_install(listing.id)
        return InstallResult(install=install, agent_id=agent_id, created=True)

    async def list_installs(
        self, *, workspace_id: str, limit: int = 50
    ) -> list[MarketplaceInstall]:
        return await self.installs.list_for_workspace(
            workspace_id=workspace_id, limit=min(max(limit, 1), 200)
        )

    async def upgrade_available(
        self, *, install: MarketplaceInstall
    ) -> tuple[Listing, bool] | None:
        """The listing this install came from, and whether it has moved on.

        `None` when the listing has since been withdrawn — there is
        nothing to offer, and the installed agent is unaffected either
        way.
        """
        listing = await self.listings.get_by_id(install.listing_id)
        if listing is None or not is_public(listing.status):
            return None
        return listing, is_upgrade(
            installed_version=install.version_number,
            latest_version=listing.latest_version,
        )

    async def reconcile_install_count(self, listing_id: str) -> int | None:
        """The true install count when it disagrees with the stored one.

        `None` when they already agree. Reports rather than repairs, for
        the same reason `reconcile_ratings` does: a disagreement means
        something wrote the denormalized column outside the transaction
        that owns it, and that is worth a human looking at.
        """
        listing = await self.listings.get_by_id(listing_id)
        if listing is None:
            return None
        actual = await self.installs.count_for_listing(listing_id)
        return None if actual == listing.install_count else actual


@dataclass(slots=True)
class ModerationService:
    """The platform-staff view of the catalog.

    Separate from `MarketplaceService` because the authority is different
    in kind: these actions are taken *about* a workspace's listing by
    someone outside it, and no workspace role can express that. The
    routes are gated by `require_platform_admin`, and every action is
    audit-logged with the acting user — a listing appearing on a public
    page is precisely the change an incident review needs to attribute.
    """

    listings: ListingRepository

    async def queue(self, *, limit: int = 50) -> list[Listing]:
        """Everything waiting on a decision, oldest first.

        Oldest first because a moderation queue sorted newest-first
        starves its tail: the listing nobody looked at yesterday is the
        one most in need of looking at today.
        """
        return await self.listings.list_by_status(
            status=ListingStatus.PENDING_REVIEW, limit=min(max(limit, 1), 200)
        )
