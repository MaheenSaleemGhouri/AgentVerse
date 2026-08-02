"""`/api/v1/workspaces` — workspace CRUD and membership (CLAUDE.md §7 REST conventions)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.application.workspace_service import WorkspaceService
from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.domain.exceptions import (
    LastOwnerError,
    UserAlreadyMemberError,
    WorkspaceSlugTakenError,
)
from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.infrastructure.repositories import SqlWorkspaceRepository
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
)
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_admin,
    require_owner,
    require_viewer,
)
from agentverse_api.auth_service.interface.dependencies.services import get_workspace_service
from agentverse_api.auth_service.interface.schemas.workspace import (
    ChangeMemberRoleRequest,
    CreateWorkspaceRequest,
    InviteMemberRequest,
    MemberResponse,
    WorkspaceResponse,
)
from agentverse_api.infrastructure.db import get_db_session

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceResponse])
async def list_my_workspaces(
    user_id: str = Depends(get_current_identity),
    service: WorkspaceService = Depends(get_workspace_service),
) -> list[WorkspaceResponse]:
    summaries = await service.list_workspaces_for_user(user_id)
    return [
        WorkspaceResponse(
            id=summary.workspace.id,
            name=summary.workspace.name,
            slug=summary.workspace.slug,
            created_at=summary.workspace.created_at,
            role=summary.role,
            organization_id=summary.workspace.organization_id,
        )
        for summary in summaries
    ]


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: CreateWorkspaceRequest,
    user_id: str = Depends(get_current_identity),
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceResponse:
    try:
        workspace = await service.create_workspace(name=body.name, owner_user_id=user_id)
    except WorkspaceSlugTakenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        created_at=workspace.created_at,
        role=Role.OWNER,
        organization_id=workspace.organization_id,
    )


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    context: WorkspaceContext = Depends(require_viewer),
    session: AsyncSession = Depends(get_db_session),
) -> WorkspaceResponse:
    repo = SqlWorkspaceRepository(session)
    workspace = await repo.get_workspace(context.workspace_id)
    if workspace is None:
        # Membership existed but the workspace row didn't — data integrity
        # issue, not a normal not-found; still surfaces as 404 to the caller.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        created_at=workspace.created_at,
        role=context.role,
        organization_id=workspace.organization_id,
    )


@router.get("/{workspace_id}/members", response_model=list[MemberResponse])
async def list_members(
    context: WorkspaceContext = Depends(require_viewer),
    service: WorkspaceService = Depends(get_workspace_service),
) -> list[MemberResponse]:
    members = await service.list_members(context.workspace_id)
    return [MemberResponse.model_validate(member, from_attributes=True) for member in members]


@router.post(
    "/{workspace_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED
)
async def invite_member(
    body: InviteMemberRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: WorkspaceService = Depends(get_workspace_service),
) -> MemberResponse:
    try:
        member = await service.invite_member(
            workspace_id=context.workspace_id,
            inviter_user_id=context.user_id,
            invitee_user_id=body.user_id,
            role=body.role,
        )
    except UserAlreadyMemberError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return MemberResponse.model_validate(member, from_attributes=True)


@router.patch("/{workspace_id}/members/{target_user_id}", response_model=MemberResponse)
async def change_member_role(
    target_user_id: str,
    body: ChangeMemberRoleRequest,
    context: WorkspaceContext = Depends(require_owner),
    service: WorkspaceService = Depends(get_workspace_service),
) -> MemberResponse:
    try:
        member = await service.change_member_role(
            workspace_id=context.workspace_id,
            actor_user_id=context.user_id,
            target_user_id=target_user_id,
            new_role=body.role,
        )
    except LastOwnerError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return MemberResponse.model_validate(member, from_attributes=True)


@router.delete(
    "/{workspace_id}/members/{target_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def remove_member(
    target_user_id: str,
    context: WorkspaceContext = Depends(require_owner),
    service: WorkspaceService = Depends(get_workspace_service),
) -> None:
    try:
        await service.remove_member(
            workspace_id=context.workspace_id,
            actor_user_id=context.user_id,
            target_user_id=target_user_id,
        )
    except LastOwnerError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
