"""`/api/v1/workspaces/{workspace_id}/api-keys` (docs/roadmap.md Phase 1 technical tasks)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from agentverse_api.auth_service.application.api_key_service import ApiKeyService, IssuedApiKey
from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.domain.exceptions import ApiKeyNotFoundError
from agentverse_api.auth_service.interface.dependencies.require_role import require_admin
from agentverse_api.auth_service.interface.dependencies.services import get_api_key_service
from agentverse_api.auth_service.interface.schemas.api_key import (
    ApiKeyResponse,
    IssueApiKeyRequest,
    IssuedApiKeyResponse,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/api-keys", tags=["api-keys"])


def _issued_response(issued: IssuedApiKey) -> IssuedApiKeyResponse:
    return IssuedApiKeyResponse(
        id=issued.entity.id,
        workspace_id=issued.entity.workspace_id,
        name=issued.entity.name,
        key_prefix=issued.entity.key_prefix,
        created_at=issued.entity.created_at,
        last_used_at=issued.entity.last_used_at,
        revoked_at=issued.entity.revoked_at,
        scope=issued.entity.scope,
        tier=issued.entity.tier,
        rotated_from_id=issued.entity.rotated_from_id,
        expires_at=issued.entity.expires_at,
        use_count=issued.entity.use_count,
        key=issued.plaintext_key,
    )


@router.post("", response_model=IssuedApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def issue_api_key(
    body: IssueApiKeyRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: ApiKeyService = Depends(get_api_key_service),
) -> IssuedApiKeyResponse:
    issued = await service.issue_api_key(
        workspace_id=context.workspace_id,
        name=body.name,
        created_by_user_id=context.user_id,
        scope=body.scope,
        tier=body.tier,
        expires_in_days=body.expires_in_days,
    )
    return _issued_response(issued)


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    context: WorkspaceContext = Depends(require_admin),
    service: ApiKeyService = Depends(get_api_key_service),
) -> list[ApiKeyResponse]:
    keys = await service.list_api_keys(context.workspace_id)
    return [ApiKeyResponse.model_validate(key, from_attributes=True) for key in keys]


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def revoke_api_key(
    api_key_id: str,
    context: WorkspaceContext = Depends(require_admin),
    service: ApiKeyService = Depends(get_api_key_service),
) -> None:
    try:
        await service.revoke_api_key(
            workspace_id=context.workspace_id,
            api_key_id=api_key_id,
            actor_user_id=context.user_id,
        )
    except ApiKeyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="API key not found"
        ) from exc


@router.post(
    "/{api_key_id}/rotate", response_model=IssuedApiKeyResponse, status_code=status.HTTP_201_CREATED
)
async def rotate_api_key(
    api_key_id: str,
    context: WorkspaceContext = Depends(require_admin),
    service: ApiKeyService = Depends(get_api_key_service),
) -> IssuedApiKeyResponse:
    try:
        issued = await service.rotate_api_key(
            workspace_id=context.workspace_id,
            api_key_id=api_key_id,
            actor_user_id=context.user_id,
        )
    except ApiKeyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="API key not found"
        ) from exc
    return _issued_response(issued)
