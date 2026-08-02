"""`/api/v1/organizations/{organization_id}/sso` — org-scoped SSO
configuration (Increment 8). Org-admin gated: SSO decides who can get
into the organization at all.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from agentverse_api.auth_service.application.sso_service import SsoService
from agentverse_api.auth_service.domain.entities import OrganizationContext
from agentverse_api.auth_service.interface.dependencies.require_org_role import (
    require_org_admin,
)
from agentverse_api.auth_service.interface.dependencies.services import get_sso_service
from agentverse_api.auth_service.interface.schemas.sso import (
    SaveSsoConfigurationRequest,
    SsoConfigurationResponse,
)

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/sso", tags=["sso"]
)


@router.get("", response_model=list[SsoConfigurationResponse])
async def list_sso_configurations(
    context: OrganizationContext = Depends(require_org_admin),
    service: SsoService = Depends(get_sso_service),
) -> list[SsoConfigurationResponse]:
    configs = await service.list_configurations(context.organization_id)
    return [
        SsoConfigurationResponse.model_validate(config, from_attributes=True)
        for config in configs
    ]


@router.put("", response_model=SsoConfigurationResponse)
async def save_sso_configuration(
    body: SaveSsoConfigurationRequest,
    context: OrganizationContext = Depends(require_org_admin),
    service: SsoService = Depends(get_sso_service),
) -> SsoConfigurationResponse:
    config = await service.save_configuration(
        organization_id=context.organization_id,
        protocol=body.protocol,
        preset=body.preset,
        issuer_url=body.issuer_url,
        client_id=body.client_id,
        client_secret=body.client_secret,
        protocol_config=body.protocol_config,
        enabled=body.enabled,
        actor_user_id=context.user_id,
    )
    return SsoConfigurationResponse.model_validate(config, from_attributes=True)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_sso_configuration(
    config_id: str,
    context: OrganizationContext = Depends(require_org_admin),
    service: SsoService = Depends(get_sso_service),
) -> None:
    await service.delete_configuration(
        organization_id=context.organization_id,
        config_id=config_id,
        actor_user_id=context.user_id,
    )
