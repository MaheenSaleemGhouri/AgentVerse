"""`/api/v1/workspaces/{workspace_id}/resource-permissions` — grant/list/
revoke resource-scoped permissions (Increment 6, CLAUDE.md §7 REST
conventions). Admin-gated: granting a permission is itself a
sensitive access-control action.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from agentverse_api.auth_service.application.resource_permission_service import (
    ResourcePermissionService,
)
from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import require_admin
from agentverse_api.auth_service.interface.dependencies.services import (
    get_resource_permission_service,
)
from agentverse_api.auth_service.interface.schemas.resource_permission import (
    GrantResourcePermissionRequest,
    ResourcePermissionResponse,
)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/resource-permissions",
    tags=["resource-permissions"],
)


@router.get("", response_model=list[ResourcePermissionResponse])
async def list_resource_permissions(
    context: WorkspaceContext = Depends(require_admin),
    service: ResourcePermissionService = Depends(get_resource_permission_service),
) -> list[ResourcePermissionResponse]:
    grants = await service.list_for_workspace(context.workspace_id)
    return [
        ResourcePermissionResponse.model_validate(grant, from_attributes=True) for grant in grants
    ]


@router.post("", response_model=ResourcePermissionResponse, status_code=status.HTTP_201_CREATED)
async def grant_resource_permission(
    body: GrantResourcePermissionRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: ResourcePermissionService = Depends(get_resource_permission_service),
) -> ResourcePermissionResponse:
    grant = await service.grant(
        workspace_id=context.workspace_id,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        principal_id=body.principal_id,
        permission=body.permission,
        granted_by_user_id=context.user_id,
    )
    return ResourcePermissionResponse.model_validate(grant, from_attributes=True)


@router.delete("/{permission_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def revoke_resource_permission(
    permission_id: str,
    context: WorkspaceContext = Depends(require_admin),
    service: ResourcePermissionService = Depends(get_resource_permission_service),
) -> None:
    await service.revoke(
        workspace_id=context.workspace_id,
        permission_id=permission_id,
        actor_user_id=context.user_id,
    )
