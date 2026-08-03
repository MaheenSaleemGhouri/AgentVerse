"""Organization profile and branding — the org-level counterpart to
`workspace_settings_service`.

Deliberately a separate use case rather than a generalised
"settings service" over both: the two have different fields, different
audiences (org admins vs workspace admins) and different authorization
chains, and collapsing them would couple two independently-evolving
surfaces for no gain (CLAUDE.md §16 — DRY at the logic level, not
forced sharing between things that merely look alike).
"""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.entities import OrganizationSettings
from agentverse_api.auth_service.domain.ports import OrganizationSettingsRepository


@dataclass(slots=True)
class OrganizationSettingsService:
    settings: OrganizationSettingsRepository
    audit: AuditService

    async def get_settings(self, organization_id: str) -> OrganizationSettings | None:
        """`None` is a real state — every organization created before this
        endpoint shipped has no row. The interface layer presents it as
        documented defaults, never a 404.
        """
        return await self.settings.get(organization_id)

    async def update_settings(
        self,
        *,
        organization_id: str,
        actor_user_id: str,
        logo_url: str | None,
        brand_color: str | None,
        custom_domain: str | None,
        website_url: str | None,
        support_email: str | None,
        description: str | None,
    ) -> OrganizationSettings:
        updated = await self.settings.upsert(
            organization_id=organization_id,
            logo_url=logo_url,
            brand_color=brand_color,
            custom_domain=custom_domain,
            website_url=website_url,
            support_email=support_email,
            description=description,
            updated_by_user_id=actor_user_id,
        )
        await self.audit.record(
            action="organization.settings_updated",
            outcome="success",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
        )
        return updated
