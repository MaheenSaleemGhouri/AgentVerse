"""`/api/v1/organizations` — organization CRUD, membership, and the
workspace attach/detach composition (ADR-0006, CLAUDE.md §7 REST
conventions).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.application.organization_service import OrganizationService
from agentverse_api.auth_service.domain.entities import OrganizationContext, WorkspaceContext
from agentverse_api.auth_service.domain.exceptions import (
    LastOrgOwnerError,
    OrganizationSlugTakenError,
    UserAlreadyOrgMemberError,
)
from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.infrastructure.repositories import SqlOrganizationRepository
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
)
from agentverse_api.auth_service.interface.dependencies.require_org_role import (
    require_org_admin,
    require_org_owner,
    require_org_viewer,
)
from agentverse_api.auth_service.interface.dependencies.require_role import require_owner
from agentverse_api.auth_service.interface.dependencies.services import get_organization_service
from agentverse_api.auth_service.interface.schemas.organization import (
    ChangeOrgMemberRoleRequest,
    CreateOrganizationRequest,
    InviteOrgMemberRequest,
    OrganizationMemberResponse,
    OrganizationResponse,
    OrganizationWorkspaceResponse,
    RenameOrganizationRequest,
)
from agentverse_api.infrastructure.db import get_db_session

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])


@router.get("", response_model=list[OrganizationResponse])
async def list_my_organizations(
    user_id: str = Depends(get_current_identity),
    service: OrganizationService = Depends(get_organization_service),
) -> list[OrganizationResponse]:
    summaries = await service.list_organizations_for_user(user_id)
    return [
        OrganizationResponse(
            id=summary.organization.id,
            name=summary.organization.name,
            slug=summary.organization.slug,
            created_at=summary.organization.created_at,
            role=summary.role,
        )
        for summary in summaries
    ]


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: CreateOrganizationRequest,
    user_id: str = Depends(get_current_identity),
    service: OrganizationService = Depends(get_organization_service),
) -> OrganizationResponse:
    try:
        organization = await service.create_organization(name=body.name, owner_user_id=user_id)
    except OrganizationSlugTakenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return OrganizationResponse(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        created_at=organization.created_at,
        role=Role.OWNER,
    )


@router.get("/{organization_id}", response_model=OrganizationResponse)
async def get_organization(
    context: OrganizationContext = Depends(require_org_viewer),
    session: AsyncSession = Depends(get_db_session),
) -> OrganizationResponse:
    repo = SqlOrganizationRepository(session)
    organization = await repo.get_organization(context.organization_id)
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )
    return OrganizationResponse(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        created_at=organization.created_at,
        role=context.role,
    )


@router.patch("/{organization_id}", response_model=OrganizationResponse)
async def rename_organization(
    body: RenameOrganizationRequest,
    context: OrganizationContext = Depends(require_org_admin),
    service: OrganizationService = Depends(get_organization_service),
) -> OrganizationResponse:
    organization = await service.rename_organization(
        organization_id=context.organization_id, actor_user_id=context.user_id, name=body.name
    )
    return OrganizationResponse(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        created_at=organization.created_at,
        role=context.role,
    )


@router.delete(
    "/{organization_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def delete_organization(
    context: OrganizationContext = Depends(require_org_owner),
    service: OrganizationService = Depends(get_organization_service),
) -> None:
    await service.delete_organization(
        organization_id=context.organization_id, actor_user_id=context.user_id
    )


@router.get("/{organization_id}/members", response_model=list[OrganizationMemberResponse])
async def list_org_members(
    context: OrganizationContext = Depends(require_org_viewer),
    service: OrganizationService = Depends(get_organization_service),
) -> list[OrganizationMemberResponse]:
    members = await service.list_members(context.organization_id)
    return [
        OrganizationMemberResponse.model_validate(member, from_attributes=True)
        for member in members
    ]


@router.post(
    "/{organization_id}/members",
    response_model=OrganizationMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_org_member(
    body: InviteOrgMemberRequest,
    context: OrganizationContext = Depends(require_org_admin),
    service: OrganizationService = Depends(get_organization_service),
) -> OrganizationMemberResponse:
    try:
        member = await service.invite_member(
            organization_id=context.organization_id,
            inviter_user_id=context.user_id,
            invitee_user_id=body.user_id,
            role=body.role,
        )
    except UserAlreadyOrgMemberError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return OrganizationMemberResponse.model_validate(member, from_attributes=True)


@router.patch(
    "/{organization_id}/members/{target_user_id}", response_model=OrganizationMemberResponse
)
async def change_org_member_role(
    target_user_id: str,
    body: ChangeOrgMemberRoleRequest,
    context: OrganizationContext = Depends(require_org_owner),
    service: OrganizationService = Depends(get_organization_service),
) -> OrganizationMemberResponse:
    try:
        member = await service.change_member_role(
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            target_user_id=target_user_id,
            new_role=body.role,
        )
    except LastOrgOwnerError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return OrganizationMemberResponse.model_validate(member, from_attributes=True)


@router.post(
    "/{organization_id}/members/{target_user_id}/suspend",
    response_model=OrganizationMemberResponse,
)
async def suspend_org_member(
    target_user_id: str,
    context: OrganizationContext = Depends(require_org_owner),
    service: OrganizationService = Depends(get_organization_service),
) -> OrganizationMemberResponse:
    try:
        member = await service.suspend_member(
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            target_user_id=target_user_id,
        )
    except LastOrgOwnerError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return OrganizationMemberResponse.model_validate(member, from_attributes=True)


@router.post(
    "/{organization_id}/members/{target_user_id}/reinstate",
    response_model=OrganizationMemberResponse,
)
async def reinstate_org_member(
    target_user_id: str,
    context: OrganizationContext = Depends(require_org_owner),
    service: OrganizationService = Depends(get_organization_service),
) -> OrganizationMemberResponse:
    member = await service.reinstate_member(
        organization_id=context.organization_id,
        actor_user_id=context.user_id,
        target_user_id=target_user_id,
    )
    return OrganizationMemberResponse.model_validate(member, from_attributes=True)


@router.delete(
    "/{organization_id}/members/{target_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def remove_org_member(
    target_user_id: str,
    context: OrganizationContext = Depends(require_org_owner),
    service: OrganizationService = Depends(get_organization_service),
) -> None:
    try:
        await service.remove_member(
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            target_user_id=target_user_id,
        )
    except LastOrgOwnerError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/{organization_id}/workspaces", response_model=list[OrganizationWorkspaceResponse]
)
async def list_org_workspaces(
    context: OrganizationContext = Depends(require_org_viewer),
    service: OrganizationService = Depends(get_organization_service),
) -> list[OrganizationWorkspaceResponse]:
    workspaces = await service.list_workspaces(context.organization_id)
    return [
        OrganizationWorkspaceResponse(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            created_at=workspace.created_at,
        )
        for workspace in workspaces
    ]


@router.post(
    "/{organization_id}/workspaces/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def attach_workspace(
    org_context: OrganizationContext = Depends(require_org_admin),
    # Composed independently of `org_context` (ADR-0006): the caller must
    # separately be the *workspace's* owner, not just an org admin — org
    # administration never implies workspace access on its own.
    workspace_context: WorkspaceContext = Depends(require_owner),
    service: OrganizationService = Depends(get_organization_service),
) -> None:
    await service.attach_workspace(
        organization_id=org_context.organization_id,
        actor_user_id=org_context.user_id,
        workspace_id=workspace_context.workspace_id,
    )


@router.delete(
    "/{organization_id}/workspaces/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def detach_workspace(
    org_context: OrganizationContext = Depends(require_org_admin),
    workspace_context: WorkspaceContext = Depends(require_owner),
    service: OrganizationService = Depends(get_organization_service),
) -> None:
    await service.detach_workspace(
        organization_id=org_context.organization_id,
        actor_user_id=org_context.user_id,
        workspace_id=workspace_context.workspace_id,
    )
