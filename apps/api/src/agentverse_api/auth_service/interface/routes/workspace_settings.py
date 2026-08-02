"""`/api/v1/workspaces/{workspace_id}/settings` — workspace-wide
branding/policy (CLAUDE.md §7 REST conventions).

`GET` is `require_viewer`: every member can see the workspace's
branding. `PATCH` is `require_admin`: only an admin/owner can change it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agentverse_api.auth_service.application.workspace_settings_service import (
    WorkspaceSettingsService,
)
from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_admin,
    require_viewer,
)
from agentverse_api.auth_service.interface.dependencies.services import (
    get_workspace_settings_service,
)
from agentverse_api.auth_service.interface.schemas.workspace_settings import (
    UpdateWorkspaceSettingsRequest,
    WorkspaceSettingsResponse,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspace-settings"])


@router.get("/{workspace_id}/settings", response_model=WorkspaceSettingsResponse)
async def get_workspace_settings_route(
    context: WorkspaceContext = Depends(require_viewer),
    service: WorkspaceSettingsService = Depends(get_workspace_settings_service),
) -> WorkspaceSettingsResponse:
    settings = await service.get_settings(context.workspace_id)
    if settings is None:
        # No settings row yet — the documented default, not a 404. Every
        # workspace created before this endpoint shipped is in this state.
        return WorkspaceSettingsResponse(
            workspace_id=context.workspace_id,
            logo_url=None,
            brand_color=None,
            custom_domain=None,
            retention_days=None,
            storage_limit_mb=None,
            updated_at=None,
            updated_by_user_id=None,
        )
    return WorkspaceSettingsResponse(
        workspace_id=settings.workspace_id,
        logo_url=settings.logo_url,
        brand_color=settings.brand_color,
        custom_domain=settings.custom_domain,
        retention_days=settings.retention_days,
        storage_limit_mb=settings.storage_limit_mb,
        updated_at=settings.updated_at,
        updated_by_user_id=settings.updated_by_user_id,
    )


@router.patch("/{workspace_id}/settings", response_model=WorkspaceSettingsResponse)
async def update_workspace_settings_route(
    body: UpdateWorkspaceSettingsRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: WorkspaceSettingsService = Depends(get_workspace_settings_service),
) -> WorkspaceSettingsResponse:
    settings = await service.update_settings(
        workspace_id=context.workspace_id,
        actor_user_id=context.user_id,
        logo_url=body.logo_url,
        brand_color=body.brand_color,
        custom_domain=body.custom_domain,
        retention_days=body.retention_days,
        storage_limit_mb=body.storage_limit_mb,
    )
    return WorkspaceSettingsResponse(
        workspace_id=settings.workspace_id,
        logo_url=settings.logo_url,
        brand_color=settings.brand_color,
        custom_domain=settings.custom_domain,
        retention_days=settings.retention_days,
        storage_limit_mb=settings.storage_limit_mb,
        updated_at=settings.updated_at,
        updated_by_user_id=settings.updated_by_user_id,
    )
