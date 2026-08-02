"""Email-based invitations for workspaces and organizations.

An email matching an existing account falls through to the existing,
unchanged `WorkspaceService.invite_member`/`OrganizationService.invite_member`
— immediate membership, exactly like today's invite-by-user-id flow. An
email with no matching account creates a token (`verifications` row,
ADR-0005) and dispatches an email; accepting it later performs the same
existing `invite_member` call, crediting the *original* inviter (carried
through the token) rather than whoever clicks accept.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.application.organization_service import OrganizationService
from agentverse_api.auth_service.application.workspace_service import WorkspaceService
from agentverse_api.auth_service.domain.entities import Invitation
from agentverse_api.auth_service.domain.exceptions import (
    InvitationAlreadyConsumedError,
    InvitationEmailMismatchError,
    InvitationExpiredError,
    InvitationNotFoundError,
)
from agentverse_api.auth_service.domain.invitation_target_type import InvitationTargetType
from agentverse_api.auth_service.domain.ports import (
    EmailSender,
    InvitationRepository,
    UserLookupRepository,
)
from agentverse_api.auth_service.domain.role import Role

_TOKEN_BYTES = 32
_INVITE_EXPIRES_AFTER = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class InviteByEmailResult:
    #: "added" when the email matched an existing account (immediate
    #: membership, no token); "invited" when a token was created and an
    #: email dispatched.
    status: str
    email: str
    role: Role


@dataclass(frozen=True, slots=True)
class AcceptInviteResult:
    target_type: InvitationTargetType
    target_id: str


@dataclass(slots=True)
class InvitationService:
    invitations: InvitationRepository
    users: UserLookupRepository
    email_sender: EmailSender
    workspaces: WorkspaceService
    organizations: OrganizationService
    audit: AuditService
    #: apps/web's public origin — the invite link points at its
    #: `/invite/accept` page, never at apps/api directly.
    web_public_url: str

    async def invite_workspace_member_by_email(
        self, *, workspace_id: str, inviter_user_id: str, email: str, role: Role
    ) -> InviteByEmailResult:
        existing = await self.users.get_by_email(email)
        if existing is not None:
            await self.workspaces.invite_member(
                workspace_id=workspace_id,
                inviter_user_id=inviter_user_id,
                invitee_user_id=existing.id,
                role=role,
            )
            return InviteByEmailResult(status="added", email=email, role=role)

        await self._create_and_send(
            target_type=InvitationTargetType.WORKSPACE,
            target_id=workspace_id,
            inviter_user_id=inviter_user_id,
            email=email,
            role=role,
        )
        return InviteByEmailResult(status="invited", email=email, role=role)

    async def invite_organization_member_by_email(
        self, *, organization_id: str, inviter_user_id: str, email: str, role: Role
    ) -> InviteByEmailResult:
        existing = await self.users.get_by_email(email)
        if existing is not None:
            await self.organizations.invite_member(
                organization_id=organization_id,
                inviter_user_id=inviter_user_id,
                invitee_user_id=existing.id,
                role=role,
            )
            return InviteByEmailResult(status="added", email=email, role=role)

        await self._create_and_send(
            target_type=InvitationTargetType.ORGANIZATION,
            target_id=organization_id,
            inviter_user_id=inviter_user_id,
            email=email,
            role=role,
        )
        return InviteByEmailResult(status="invited", email=email, role=role)

    async def _create_and_send(
        self,
        *,
        target_type: InvitationTargetType,
        target_id: str,
        inviter_user_id: str,
        email: str,
        role: Role,
    ) -> Invitation:
        token = secrets.token_urlsafe(_TOKEN_BYTES)
        invitation = await self.invitations.create(
            target_type=target_type,
            target_id=target_id,
            role=role,
            inviter_user_id=inviter_user_id,
            email=email,
            token=token,
            expires_at=datetime.now(UTC) + _INVITE_EXPIRES_AFTER,
        )
        link = f"{self.web_public_url}/invite/accept?token={token}"
        noun = "workspace" if target_type is InvitationTargetType.WORKSPACE else "organization"
        await self.email_sender.send(
            to=email,
            subject="You've been invited to AgentVerse",
            body=f"You've been invited to join a {noun} on AgentVerse. Accept: {link}",
        )
        await self.audit.record(
            action="invitation.sent",
            outcome="success",
            workspace_id=target_id if target_type is InvitationTargetType.WORKSPACE else None,
            organization_id=(
                target_id if target_type is InvitationTargetType.ORGANIZATION else None
            ),
            actor_user_id=inviter_user_id,
            target=email,
            metadata={"role": role.value},
        )
        return invitation

    async def accept_invite(self, *, token: str, accepting_user_id: str) -> AcceptInviteResult:
        invitation = await self.invitations.get_by_token(token)
        if invitation is None:
            raise InvitationNotFoundError()
        if invitation.consumed_at is not None:
            raise InvitationAlreadyConsumedError()
        if invitation.expires_at <= datetime.now(UTC):
            raise InvitationExpiredError()

        accepting_user = await self.users.get_by_id(accepting_user_id)
        if accepting_user is None or accepting_user.email.lower() != invitation.email.lower():
            # Deliberately the same error as an expired/consumed token —
            # not "wrong email", so a stolen link cannot be used to probe
            # which email address it was sent to.
            raise InvitationEmailMismatchError()

        if invitation.target_type is InvitationTargetType.WORKSPACE:
            await self.workspaces.invite_member(
                workspace_id=invitation.target_id,
                inviter_user_id=invitation.inviter_user_id,
                invitee_user_id=accepting_user_id,
                role=invitation.role,
            )
        else:
            await self.organizations.invite_member(
                organization_id=invitation.target_id,
                inviter_user_id=invitation.inviter_user_id,
                invitee_user_id=accepting_user_id,
                role=invitation.role,
            )

        await self.invitations.consume(token)
        return AcceptInviteResult(
            target_type=invitation.target_type, target_id=invitation.target_id
        )
