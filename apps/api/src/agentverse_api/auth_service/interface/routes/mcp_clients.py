"""`/api/v1/workspaces/{workspace_id}/mcp-clients` (Phase 12, ADR-0017).

A distinct URL and response shape from `/api-keys`, but the same
`ApiKeyService`/`api_keys` table underneath (`kind='mcp_client'`) —
genuinely the same credential mechanism, kept as a separate surface so
an admin issuing an integration token for an external MCP client never
has to pick it out of a mixed personal-API-key list, and so revoking
"the Zapier integration" can't also silently revoke someone's personal
key by accident.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from agentverse_api.auth_service.application.api_key_service import ApiKeyService, IssuedApiKey
from agentverse_api.auth_service.domain.api_key_kind import ApiKeyKind
from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.domain.exceptions import ApiKeyNotFoundError
from agentverse_api.auth_service.interface.dependencies.require_role import require_admin
from agentverse_api.auth_service.interface.dependencies.services import get_api_key_service
from agentverse_api.auth_service.interface.schemas.mcp_client import (
    IssuedMcpClientResponse,
    IssueMcpClientRequest,
    McpClientResponse,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/mcp-clients", tags=["mcp-clients"])


def _issued_response(issued: IssuedApiKey) -> IssuedMcpClientResponse:
    return IssuedMcpClientResponse(
        id=issued.entity.id,
        workspace_id=issued.entity.workspace_id,
        name=issued.entity.name,
        key_prefix=issued.entity.key_prefix,
        created_at=issued.entity.created_at,
        last_used_at=issued.entity.last_used_at,
        revoked_at=issued.entity.revoked_at,
        scope=issued.entity.scope,
        expires_at=issued.entity.expires_at,
        use_count=issued.entity.use_count,
        key=issued.plaintext_key,
    )


@router.post("", response_model=IssuedMcpClientResponse, status_code=status.HTTP_201_CREATED)
async def issue_mcp_client(
    body: IssueMcpClientRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: ApiKeyService = Depends(get_api_key_service),
) -> IssuedMcpClientResponse:
    issued = await service.issue_api_key(
        workspace_id=context.workspace_id,
        name=body.name,
        created_by_user_id=context.user_id,
        scope=body.scope,
        expires_in_days=body.expires_in_days,
        kind=ApiKeyKind.MCP_CLIENT,
    )
    return _issued_response(issued)


@router.get("", response_model=list[McpClientResponse])
async def list_mcp_clients(
    context: WorkspaceContext = Depends(require_admin),
    service: ApiKeyService = Depends(get_api_key_service),
) -> list[McpClientResponse]:
    clients = await service.list_api_keys(context.workspace_id, kind=ApiKeyKind.MCP_CLIENT)
    return [McpClientResponse.model_validate(client, from_attributes=True) for client in clients]


@router.delete("/{mcp_client_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def revoke_mcp_client(
    mcp_client_id: str,
    context: WorkspaceContext = Depends(require_admin),
    service: ApiKeyService = Depends(get_api_key_service),
) -> None:
    try:
        await service.revoke_api_key(
            workspace_id=context.workspace_id,
            api_key_id=mcp_client_id,
            actor_user_id=context.user_id,
        )
    except ApiKeyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="MCP client not found"
        ) from exc
