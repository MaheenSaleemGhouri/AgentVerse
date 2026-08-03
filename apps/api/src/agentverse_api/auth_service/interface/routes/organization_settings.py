"""`/api/v1/organizations/{organization_id}/settings` — organization
profile and branding.

`GET` is `require_org_viewer` (every member can see their org's
identity); `PATCH` is `require_org_admin`. Both resolve the organization
through `get_current_organization`, so a caller who is not a member gets
a 404 rather than a 403 — an organization's existence is not leaked to
someone outside it (CLAUDE.md §10).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agentverse_api.auth_service.application.organization_settings_service import (
    OrganizationSettingsService,
)
from agentverse_api.auth_service.domain.entities import (
    OrganizationContext,
    OrganizationSettings,
)
from agentverse_api.auth_service.interface.dependencies.require_org_role import (
    require_org_admin,
    require_org_viewer,
)
from agentverse_api.auth_service.interface.dependencies.services import (
    get_organization_settings_service,
)
from agentverse_api.auth_service.interface.schemas.organization_settings import (
    OrganizationSettingsResponse,
    UpdateOrganizationSettingsRequest,
)

router = APIRouter(prefix="/api/v1/organizations", tags=["organization-settings"])


@router.get("/{organization_id}/settings", response_model=OrganizationSettingsResponse)
async def get_organization_settings_route(
    context: OrganizationContext = Depends(require_org_viewer),
    service: OrganizationSettingsService = Depends(get_organization_settings_service),
) -> OrganizationSettingsResponse:
    settings = await service.get_settings(context.organization_id)
    if settings is None:
        # Documented defaults, not a 404 — every organization created
        # before this endpoint shipped has no settings row.
        return OrganizationSettingsResponse(
            organization_id=context.organization_id,
            logo_url=None,
            brand_color=None,
            custom_domain=None,
            website_url=None,
            support_email=None,
            description=None,
            updated_at=None,
            updated_by_user_id=None,
        )
    return _to_response(settings)


@router.patch("/{organization_id}/settings", response_model=OrganizationSettingsResponse)
async def update_organization_settings_route(
    body: UpdateOrganizationSettingsRequest,
    context: OrganizationContext = Depends(require_org_admin),
    service: OrganizationSettingsService = Depends(get_organization_settings_service),
) -> OrganizationSettingsResponse:
    settings = await service.update_settings(
        organization_id=context.organization_id,
        actor_user_id=context.user_id,
        logo_url=body.logo_url,
        brand_color=body.brand_color,
        custom_domain=body.custom_domain,
        website_url=body.website_url,
        support_email=body.support_email,
        description=body.description,
    )
    return _to_response(settings)


def _to_response(settings: OrganizationSettings) -> OrganizationSettingsResponse:
    return OrganizationSettingsResponse(
        organization_id=settings.organization_id,
        logo_url=settings.logo_url,
        brand_color=settings.brand_color,
        custom_domain=settings.custom_domain,
        website_url=settings.website_url,
        support_email=settings.support_email,
        description=settings.description,
        updated_at=settings.updated_at,
        updated_by_user_id=settings.updated_by_user_id,
    )
