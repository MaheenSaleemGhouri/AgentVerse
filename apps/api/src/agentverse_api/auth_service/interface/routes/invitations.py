"""Email-based invitations — `/api/v1/workspaces/{id}/invitations`,
`/api/v1/organizations/{id}/invitations`, and the target-agnostic
`/api/v1/invitations/accept` (CLAUDE.md §7 REST conventions).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from agentverse_api.auth_service.application.invitation_service import InvitationService
from agentverse_api.auth_service.domain.entities import OrganizationContext, WorkspaceContext
from agentverse_api.auth_service.domain.exceptions import (
    InvitationAlreadyConsumedError,
    InvitationEmailMismatchError,
    InvitationExpiredError,
    InvitationNotFoundError,
    UserAlreadyMemberError,
    UserAlreadyOrgMemberError,
)
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
)
from agentverse_api.auth_service.interface.dependencies.require_org_role import require_org_admin
from agentverse_api.auth_service.interface.dependencies.require_role import require_admin
from agentverse_api.auth_service.interface.dependencies.services import get_invitation_service
from agentverse_api.auth_service.interface.schemas.invitation import (
    AcceptInviteRequest,
    AcceptInviteResponse,
    InviteByEmailRequest,
    InviteByEmailResponse,
)

router = APIRouter(prefix="/api/v1", tags=["invitations"])


@router.post(
    "/workspaces/{workspace_id}/invitations",
    response_model=InviteByEmailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_workspace_member_by_email(
    body: InviteByEmailRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: InvitationService = Depends(get_invitation_service),
) -> InviteByEmailResponse:
    try:
        result = await service.invite_workspace_member_by_email(
            workspace_id=context.workspace_id,
            inviter_user_id=context.user_id,
            email=body.email,
            role=body.role,
        )
    except UserAlreadyMemberError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return InviteByEmailResponse(status=result.status, email=result.email, role=result.role)


@router.post(
    "/organizations/{organization_id}/invitations",
    response_model=InviteByEmailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_organization_member_by_email(
    body: InviteByEmailRequest,
    context: OrganizationContext = Depends(require_org_admin),
    service: InvitationService = Depends(get_invitation_service),
) -> InviteByEmailResponse:
    try:
        result = await service.invite_organization_member_by_email(
            organization_id=context.organization_id,
            inviter_user_id=context.user_id,
            email=body.email,
            role=body.role,
        )
    except UserAlreadyOrgMemberError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return InviteByEmailResponse(status=result.status, email=result.email, role=result.role)


@router.post("/invitations/accept", response_model=AcceptInviteResponse)
async def accept_invite(
    body: AcceptInviteRequest,
    user_id: str = Depends(get_current_identity),
    service: InvitationService = Depends(get_invitation_service),
) -> AcceptInviteResponse:
    # Depends only on identity, never on workspace/org membership — the
    # caller isn't a member of the target yet; the token itself carries
    # and authorizes the target (ADR-0004's pattern extended to a
    # not-yet-a-member caller).
    try:
        result = await service.accept_invite(token=body.token, accepting_user_id=user_id)
    except InvitationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (
        InvitationAlreadyConsumedError,
        InvitationExpiredError,
        InvitationEmailMismatchError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except (UserAlreadyMemberError, UserAlreadyOrgMemberError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return AcceptInviteResponse(target_type=result.target_type, target_id=result.target_id)
