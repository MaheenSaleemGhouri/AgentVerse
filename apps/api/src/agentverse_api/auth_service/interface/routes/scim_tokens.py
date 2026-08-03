"""`/api/v1/organizations/{organization_id}/scim-tokens` — the admin
surface for the credentials an identity provider uses against
`/scim/v2`.

Org-admin gated for the same reason SSO configuration is: a SCIM token
can create and deprovision the organization's people.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from agentverse_api.auth_service.application.scim_service import IssuedScimToken, ScimService
from agentverse_api.auth_service.domain.entities import OrganizationContext
from agentverse_api.auth_service.interface.dependencies.require_org_role import (
    require_org_admin,
)
from agentverse_api.auth_service.interface.dependencies.services import get_scim_service
from agentverse_api.auth_service.interface.schemas.scim import (
    IssuedScimTokenResponse,
    IssueScimTokenRequest,
    ScimTokenResponse,
)

router = APIRouter(
    prefix="/api/v1/organizations/{organization_id}/scim-tokens", tags=["scim-tokens"]
)


@router.post("", response_model=IssuedScimTokenResponse, status_code=status.HTTP_201_CREATED)
async def issue_scim_token(
    body: IssueScimTokenRequest,
    context: OrganizationContext = Depends(require_org_admin),
    service: ScimService = Depends(get_scim_service),
) -> IssuedScimTokenResponse:
    issued: IssuedScimToken = await service.issue_token(
        organization_id=context.organization_id,
        name=body.name,
        actor_user_id=context.user_id,
    )
    return IssuedScimTokenResponse(
        id=issued.entity.id,
        organization_id=issued.entity.organization_id,
        name=issued.entity.name,
        token_prefix=issued.entity.token_prefix,
        created_at=issued.entity.created_at,
        last_used_at=issued.entity.last_used_at,
        revoked_at=issued.entity.revoked_at,
        token=issued.plaintext_token,
    )


@router.get("", response_model=list[ScimTokenResponse])
async def list_scim_tokens(
    context: OrganizationContext = Depends(require_org_admin),
    service: ScimService = Depends(get_scim_service),
) -> list[ScimTokenResponse]:
    tokens = await service.list_tokens(context.organization_id)
    return [ScimTokenResponse.model_validate(token, from_attributes=True) for token in tokens]


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def revoke_scim_token(
    token_id: str,
    context: OrganizationContext = Depends(require_org_admin),
    service: ScimService = Depends(get_scim_service),
) -> None:
    revoked = await service.revoke_token(
        organization_id=context.organization_id,
        token_id=token_id,
        actor_user_id=context.user_id,
    )
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SCIM token not found")
