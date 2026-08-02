"""Workspace-wide settings — branding, custom domain, retention/storage
policy. A thin use case: `get_settings` returns `None` when no row
exists yet (a real, expected state — every pre-existing workspace has
none), and the interface layer is responsible for presenting that as
documented defaults rather than a 404.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.entities import WorkspaceSettings
from agentverse_api.auth_service.domain.ports import WorkspaceSettingsRepository


@dataclass(slots=True)
class WorkspaceSettingsService:
    settings: WorkspaceSettingsRepository
    audit: AuditService

    async def get_settings(self, workspace_id: str) -> WorkspaceSettings | None:
        return await self.settings.get(workspace_id)

    async def update_settings(
        self,
        *,
        workspace_id: str,
        actor_user_id: str,
        logo_url: str | None,
        brand_color: str | None,
        custom_domain: str | None,
        retention_days: int | None,
        storage_limit_mb: int | None,
    ) -> WorkspaceSettings:
        updated = await self.settings.upsert(
            workspace_id=workspace_id,
            logo_url=logo_url,
            brand_color=brand_color,
            custom_domain=custom_domain,
            retention_days=retention_days,
            storage_limit_mb=storage_limit_mb,
            updated_by_user_id=actor_user_id,
        )
        await self.audit.record(
            action="workspace.settings_updated",
            outcome="success",
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
        )
        return updated
