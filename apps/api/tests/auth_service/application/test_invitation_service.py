from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.application.invitation_service import InvitationService
from agentverse_api.auth_service.application.organization_service import OrganizationService
from agentverse_api.auth_service.application.workspace_service import WorkspaceService
from agentverse_api.auth_service.domain.entities import UserSummary
from agentverse_api.auth_service.domain.exceptions import (
    InvitationAlreadyConsumedError,
    InvitationEmailMismatchError,
    InvitationExpiredError,
    InvitationNotFoundError,
)
from agentverse_api.auth_service.domain.invitation_target_type import InvitationTargetType
from agentverse_api.auth_service.domain.role import Role
from tests.fakes.auth_service_repositories import (
    FakeAuditLogRepository,
    FakeEmailSender,
    FakeInvitationRepository,
    FakeOrganizationRepository,
    FakeUserLookupRepository,
    FakeWorkspaceRepository,
)


@pytest.fixture
def service() -> tuple[
    InvitationService, FakeAuditLogRepository, FakeEmailSender, FakeUserLookupRepository
]:
    audit_repo = FakeAuditLogRepository()
    audit = AuditService(audit_logs=audit_repo)
    users = FakeUserLookupRepository()
    email_sender = FakeEmailSender()
    invitation_service = InvitationService(
        invitations=FakeInvitationRepository(),
        users=users,
        email_sender=email_sender,
        workspaces=WorkspaceService(workspaces=FakeWorkspaceRepository(), audit=audit),
        organizations=OrganizationService(organizations=FakeOrganizationRepository(), audit=audit),
        audit=audit,
        web_public_url="https://app.example.com",
    )
    return invitation_service, audit_repo, email_sender, users


async def test_invite_by_email_adds_existing_user_directly_without_sending_email(
    service: tuple[
        InvitationService, FakeAuditLogRepository, FakeEmailSender, FakeUserLookupRepository
    ],
) -> None:
    invitation_service, _, email_sender, users = service
    workspace = await invitation_service.workspaces.create_workspace(
        name="Acme", owner_user_id="owner"
    )
    users.users["existing"] = UserSummary(id="existing", email="existing@example.com")

    result = await invitation_service.invite_workspace_member_by_email(
        workspace_id=workspace.id,
        inviter_user_id="owner",
        email="existing@example.com",
        role=Role.MEMBER,
    )

    assert result.status == "added"
    membership = await invitation_service.workspaces.workspaces.get_membership(
        workspace_id=workspace.id, user_id="existing"
    )
    assert membership is not None
    assert membership.role is Role.MEMBER
    assert email_sender.sent == []


async def test_invite_by_email_creates_a_token_and_sends_an_email_for_an_unknown_address(
    service: tuple[
        InvitationService, FakeAuditLogRepository, FakeEmailSender, FakeUserLookupRepository
    ],
) -> None:
    invitation_service, audit_repo, email_sender, _ = service
    workspace = await invitation_service.workspaces.create_workspace(
        name="Acme", owner_user_id="owner"
    )

    result = await invitation_service.invite_workspace_member_by_email(
        workspace_id=workspace.id,
        inviter_user_id="owner",
        email="new-person@example.com",
        role=Role.ADMIN,
    )

    assert result.status == "invited"
    assert len(email_sender.sent) == 1
    assert email_sender.sent[0]["to"] == "new-person@example.com"
    assert "https://app.example.com/invite/accept?token=" in email_sender.sent[0]["body"]
    assert any(entry.action == "invitation.sent" for entry in audit_repo.entries)

    [invitation] = invitation_service.invitations.by_token.values()
    assert invitation.role is Role.ADMIN
    assert invitation.inviter_user_id == "owner"
    assert invitation.expires_at - invitation.created_at > timedelta(days=6, hours=23)


async def test_accept_invite_creates_membership_credited_to_the_original_inviter(
    service: tuple[
        InvitationService, FakeAuditLogRepository, FakeEmailSender, FakeUserLookupRepository
    ],
) -> None:
    invitation_service, audit_repo, _, users = service

    workspace = await invitation_service.workspaces.create_workspace(
        name="Acme", owner_user_id="owner"
    )
    await invitation_service.invite_workspace_member_by_email(
        workspace_id=workspace.id,
        inviter_user_id="owner",
        email="invitee@example.com",
        role=Role.MEMBER,
    )
    [token] = invitation_service.invitations.by_token.keys()
    users.users["invitee-account"] = UserSummary(id="invitee-account", email="invitee@example.com")

    result = await invitation_service.accept_invite(
        token=token, accepting_user_id="invitee-account"
    )

    assert result.target_type is InvitationTargetType.WORKSPACE
    assert result.target_id == workspace.id
    membership = await invitation_service.workspaces.workspaces.get_membership(
        workspace_id=workspace.id, user_id="invitee-account"
    )
    assert membership is not None
    # The audit trail credits the original inviter, not the accepter —
    # acceptance can happen long after the invite was sent.
    invited_entries = [e for e in audit_repo.entries if e.action == "member.invited"]
    assert any(e.actor_user_id == "owner" for e in invited_entries)


async def test_accept_invite_a_second_time_fails_because_the_token_is_consumed(
    service: tuple[
        InvitationService, FakeAuditLogRepository, FakeEmailSender, FakeUserLookupRepository
    ],
) -> None:
    invitation_service, _, _, users = service

    workspace = await invitation_service.workspaces.create_workspace(
        name="Acme", owner_user_id="owner"
    )
    await invitation_service.invite_workspace_member_by_email(
        workspace_id=workspace.id,
        inviter_user_id="owner",
        email="invitee@example.com",
        role=Role.MEMBER,
    )
    [token] = invitation_service.invitations.by_token.keys()
    users.users["invitee-account"] = UserSummary(id="invitee-account", email="invitee@example.com")
    await invitation_service.accept_invite(token=token, accepting_user_id="invitee-account")

    with pytest.raises(InvitationAlreadyConsumedError):
        await invitation_service.accept_invite(token=token, accepting_user_id="invitee-account")


async def test_accept_invite_rejects_an_expired_token(
    service: tuple[
        InvitationService, FakeAuditLogRepository, FakeEmailSender, FakeUserLookupRepository
    ],
) -> None:
    invitation_service, _, _, users = service

    await invitation_service.invitations.create(
        target_type=InvitationTargetType.WORKSPACE,
        target_id="ws-1",
        role=Role.MEMBER,
        inviter_user_id="owner",
        email="invitee@example.com",
        token="expired-token",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    users.users["invitee-account"] = UserSummary(id="invitee-account", email="invitee@example.com")

    with pytest.raises(InvitationExpiredError):
        await invitation_service.accept_invite(
            token="expired-token", accepting_user_id="invitee-account"
        )


async def test_accept_invite_rejects_a_mismatched_accepting_email(
    service: tuple[
        InvitationService, FakeAuditLogRepository, FakeEmailSender, FakeUserLookupRepository
    ],
) -> None:
    invitation_service, _, _, users = service

    workspace = await invitation_service.workspaces.create_workspace(
        name="Acme", owner_user_id="owner"
    )
    await invitation_service.invite_workspace_member_by_email(
        workspace_id=workspace.id,
        inviter_user_id="owner",
        email="invitee@example.com",
        role=Role.MEMBER,
    )
    [token] = invitation_service.invitations.by_token.keys()
    # A different account, with a different email, tries to use the link.
    users.users["someone-else"] = UserSummary(id="someone-else", email="someone-else@example.com")

    with pytest.raises(InvitationEmailMismatchError):
        await invitation_service.accept_invite(token=token, accepting_user_id="someone-else")


async def test_accept_invite_rejects_an_unknown_token(
    service: tuple[
        InvitationService, FakeAuditLogRepository, FakeEmailSender, FakeUserLookupRepository
    ],
) -> None:
    invitation_service, _, _, _ = service

    with pytest.raises(InvitationNotFoundError):
        await invitation_service.accept_invite(token="nope", accepting_user_id="anyone")


async def test_invite_organization_member_by_email_mirrors_the_workspace_flow(
    service: tuple[
        InvitationService, FakeAuditLogRepository, FakeEmailSender, FakeUserLookupRepository
    ],
) -> None:
    invitation_service, _, email_sender, _ = service
    organization = await invitation_service.organizations.create_organization(
        name="Acme Org", owner_user_id="owner"
    )

    result = await invitation_service.invite_organization_member_by_email(
        organization_id=organization.id,
        inviter_user_id="owner",
        email="new-org-person@example.com",
        role=Role.VIEWER,
    )

    assert result.status == "invited"
    assert len(email_sender.sent) == 1
    [invitation] = invitation_service.invitations.by_token.values()
    assert invitation.target_type is InvitationTargetType.ORGANIZATION
    assert invitation.target_id == organization.id
