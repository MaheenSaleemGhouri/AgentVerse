"""`/api/v1/workspaces/{workspace_id}/roles` — the role model and
tenant-defined roles.

Reading the built-in matrix is viewer-gated: a member should be able to
see what their own role permits. Creating, changing and deleting roles is
admin-gated, because defining a role is itself an access-control action.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from agentverse_api.auth_service.application.rbac_service import RbacService
from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.domain.exceptions import (
    CustomRoleNameTakenError,
    CustomRoleNotFoundError,
    InvalidPermissionError,
)
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_admin,
    require_viewer,
)
from agentverse_api.auth_service.interface.dependencies.services import get_rbac_service
from agentverse_api.auth_service.interface.schemas.rbac import (
    CreateCustomRoleRequest,
    CustomRoleResponse,
    RoleDescriptor,
    UpdateCustomRoleRequest,
    describe_builtin_roles,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/roles", tags=["roles"])

#: 404 rather than 403 for a role belonging to another workspace — the
#: caller must not learn that the id is real elsewhere (Rule 11).
_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")


@router.get("/builtin", response_model=list[RoleDescriptor])
async def list_builtin_roles(
    _: WorkspaceContext = Depends(require_viewer),
) -> list[RoleDescriptor]:
    """The seven built-in tiers and their fully-inherited permission sets."""
    return describe_builtin_roles()


@router.get("", response_model=list[CustomRoleResponse])
async def list_custom_roles(
    context: WorkspaceContext = Depends(require_viewer),
    service: RbacService = Depends(get_rbac_service),
) -> list[CustomRoleResponse]:
    roles = await service.list_roles(context.workspace_id)
    return [CustomRoleResponse.model_validate(role, from_attributes=True) for role in roles]


@router.post("", response_model=CustomRoleResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_role(
    body: CreateCustomRoleRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: RbacService = Depends(get_rbac_service),
) -> CustomRoleResponse:
    try:
        role = await service.create_role(
            workspace_id=context.workspace_id,
            name=body.name,
            description=body.description,
            base_role=body.base_role,
            permissions=body.permissions,
            actor_user_id=context.user_id,
        )
    except InvalidPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except CustomRoleNameTakenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return CustomRoleResponse.model_validate(role, from_attributes=True)


@router.get("/{role_id}", response_model=CustomRoleResponse)
async def get_custom_role(
    role_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    service: RbacService = Depends(get_rbac_service),
) -> CustomRoleResponse:
    try:
        role = await service.get_role(workspace_id=context.workspace_id, role_id=role_id)
    except CustomRoleNotFoundError as exc:
        raise _NOT_FOUND from exc
    return CustomRoleResponse.model_validate(role, from_attributes=True)


@router.patch("/{role_id}", response_model=CustomRoleResponse)
async def update_custom_role(
    role_id: str,
    body: UpdateCustomRoleRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: RbacService = Depends(get_rbac_service),
) -> CustomRoleResponse:
    try:
        role = await service.update_role(
            workspace_id=context.workspace_id,
            role_id=role_id,
            name=body.name,
            description=body.description,
            base_role=body.base_role,
            permissions=body.permissions,
            actor_user_id=context.user_id,
        )
    except CustomRoleNotFoundError as exc:
        raise _NOT_FOUND from exc
    except InvalidPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return CustomRoleResponse.model_validate(role, from_attributes=True)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_custom_role(
    role_id: str,
    context: WorkspaceContext = Depends(require_admin),
    service: RbacService = Depends(get_rbac_service),
) -> None:
    try:
        await service.delete_role(
            workspace_id=context.workspace_id,
            role_id=role_id,
            actor_user_id=context.user_id,
        )
    except CustomRoleNotFoundError as exc:
        raise _NOT_FOUND from exc
