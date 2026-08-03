import pytest

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.application.organization_service import OrganizationService
from agentverse_api.auth_service.domain.exceptions import (
    LastOrgOwnerError,
    OrganizationSlugTakenError,
    UserAlreadyOrgMemberError,
)
from agentverse_api.auth_service.domain.role import Role
from tests.fakes.auth_service_repositories import FakeAuditLogRepository, FakeOrganizationRepository


@pytest.fixture
def service() -> tuple[OrganizationService, FakeAuditLogRepository]:
    audit_repo = FakeAuditLogRepository()
    organization_repo = FakeOrganizationRepository()
    return (
        OrganizationService(
            organizations=organization_repo, audit=AuditService(audit_logs=audit_repo)
        ),
        audit_repo,
    )


async def test_create_organization_makes_creator_owner(
    service: tuple[OrganizationService, FakeAuditLogRepository],
) -> None:
    org_service, audit_repo = service

    organization = await org_service.create_organization(name="Acme Inc.", owner_user_id="u1")

    membership = await org_service.organizations.get_membership(
        organization_id=organization.id, user_id="u1"
    )
    assert membership is not None
    assert membership.role is Role.OWNER
    assert membership.suspended_at is None
    assert any(entry.action == "organization.created" for entry in audit_repo.entries)


async def test_create_organization_resolves_slug_collision(
    service: tuple[OrganizationService, FakeAuditLogRepository],
) -> None:
    org_service, _ = service

    first = await org_service.create_organization(name="Acme", owner_user_id="u1")
    second = await org_service.create_organization(name="Acme", owner_user_id="u2")

    assert first.slug == "acme"
    assert second.slug == "acme-2"


async def test_create_organization_raises_when_all_ten_slug_candidates_taken(
    service: tuple[OrganizationService, FakeAuditLogRepository],
) -> None:
    org_service, _ = service
    for i in range(10):
        await org_service.create_organization(name="Acme", owner_user_id=f"u{i}")

    with pytest.raises(OrganizationSlugTakenError):
        await org_service.create_organization(name="Acme", owner_user_id="u-overflow")


async def test_invite_member_adds_membership_and_audits(
    service: tuple[OrganizationService, FakeAuditLogRepository],
) -> None:
    org_service, audit_repo = service
    organization = await org_service.create_organization(name="Acme", owner_user_id="owner")

    member = await org_service.invite_member(
        organization_id=organization.id,
        inviter_user_id="owner",
        invitee_user_id="new-user",
        role=Role.MEMBER,
    )

    assert member.role is Role.MEMBER
    assert any(entry.action == "organization_member.invited" for entry in audit_repo.entries)


async def test_invite_member_rejects_existing_member(
    service: tuple[OrganizationService, FakeAuditLogRepository],
) -> None:
    org_service, _ = service
    organization = await org_service.create_organization(name="Acme", owner_user_id="owner")
    await org_service.invite_member(
        organization_id=organization.id,
        inviter_user_id="owner",
        invitee_user_id="dup",
        role=Role.MEMBER,
    )

    with pytest.raises(UserAlreadyOrgMemberError):
        await org_service.invite_member(
            organization_id=organization.id,
            inviter_user_id="owner",
            invitee_user_id="dup",
            role=Role.VIEWER,
        )


async def test_change_member_role_blocks_demoting_the_last_owner(
    service: tuple[OrganizationService, FakeAuditLogRepository],
) -> None:
    org_service, _ = service
    organization = await org_service.create_organization(name="Acme", owner_user_id="sole-owner")

    with pytest.raises(LastOrgOwnerError):
        await org_service.change_member_role(
            organization_id=organization.id,
            actor_user_id="sole-owner",
            target_user_id="sole-owner",
            new_role=Role.ADMIN,
        )


async def test_change_member_role_allows_demotion_when_another_owner_exists(
    service: tuple[OrganizationService, FakeAuditLogRepository],
) -> None:
    org_service, _ = service
    organization = await org_service.create_organization(name="Acme", owner_user_id="owner1")
    await org_service.invite_member(
        organization_id=organization.id,
        inviter_user_id="owner1",
        invitee_user_id="owner2",
        role=Role.OWNER,
    )

    updated = await org_service.change_member_role(
        organization_id=organization.id,
        actor_user_id="owner2",
        target_user_id="owner1",
        new_role=Role.ADMIN,
    )

    assert updated.role is Role.ADMIN


async def test_remove_member_blocks_removing_the_last_owner(
    service: tuple[OrganizationService, FakeAuditLogRepository],
) -> None:
    org_service, _ = service
    organization = await org_service.create_organization(name="Acme", owner_user_id="sole-owner")

    with pytest.raises(LastOrgOwnerError):
        await org_service.remove_member(
            organization_id=organization.id,
            actor_user_id="sole-owner",
            target_user_id="sole-owner",
        )


async def test_suspend_member_blocks_suspending_the_last_owner(
    service: tuple[OrganizationService, FakeAuditLogRepository],
) -> None:
    """Suspension is functionally equivalent to losing access — the last
    owner cannot be locked out of their own organization any more than
    they can be removed or demoted."""
    org_service, _ = service
    organization = await org_service.create_organization(name="Acme", owner_user_id="sole-owner")

    with pytest.raises(LastOrgOwnerError):
        await org_service.suspend_member(
            organization_id=organization.id,
            actor_user_id="sole-owner",
            target_user_id="sole-owner",
        )


async def test_suspend_then_reinstate_member_round_trips(
    service: tuple[OrganizationService, FakeAuditLogRepository],
) -> None:
    org_service, audit_repo = service
    organization = await org_service.create_organization(name="Acme", owner_user_id="owner")
    await org_service.invite_member(
        organization_id=organization.id,
        inviter_user_id="owner",
        invitee_user_id="u2",
        role=Role.MEMBER,
    )

    suspended = await org_service.suspend_member(
        organization_id=organization.id, actor_user_id="owner", target_user_id="u2"
    )
    assert suspended.suspended_at is not None

    reinstated = await org_service.reinstate_member(
        organization_id=organization.id, actor_user_id="owner", target_user_id="u2"
    )
    assert reinstated.suspended_at is None
    assert any(entry.action == "organization_member.suspended" for entry in audit_repo.entries)
    assert any(entry.action == "organization_member.reinstated" for entry in audit_repo.entries)


async def test_delete_organization_detaches_but_does_not_delete_its_workspaces(
    service: tuple[OrganizationService, FakeAuditLogRepository],
) -> None:
    """The core ADR-0011 invariant, exercised at the service layer: a
    deleted organization's workspaces survive, merely detached."""
    org_service, audit_repo = service
    organization = await org_service.create_organization(name="Acme", owner_user_id="owner")
    repo = org_service.organizations
    assert isinstance(repo, FakeOrganizationRepository)
    from agentverse_api.auth_service.domain.entities import Workspace as WorkspaceEntity

    repo.workspaces["ws-1"] = WorkspaceEntity(
        id="ws-1", name="Acme Workspace", slug="acme-workspace", created_at=organization.created_at
    )
    await org_service.attach_workspace(
        organization_id=organization.id, actor_user_id="owner", workspace_id="ws-1"
    )
    assert repo.workspaces["ws-1"].organization_id == organization.id

    await org_service.delete_organization(organization_id=organization.id, actor_user_id="owner")

    assert repo.workspaces["ws-1"].organization_id is None
    assert any(entry.action == "organization.deleted" for entry in audit_repo.entries)


async def test_attach_and_detach_workspace_round_trip(
    service: tuple[OrganizationService, FakeAuditLogRepository],
) -> None:
    org_service, audit_repo = service
    organization = await org_service.create_organization(name="Acme", owner_user_id="owner")
    repo = org_service.organizations
    assert isinstance(repo, FakeOrganizationRepository)
    from agentverse_api.auth_service.domain.entities import Workspace as WorkspaceEntity

    repo.workspaces["ws-1"] = WorkspaceEntity(
        id="ws-1", name="Acme Workspace", slug="acme-workspace", created_at=organization.created_at
    )

    await org_service.attach_workspace(
        organization_id=organization.id, actor_user_id="owner", workspace_id="ws-1"
    )
    attached = await org_service.list_workspaces(organization.id)
    assert [workspace.id for workspace in attached] == ["ws-1"]

    await org_service.detach_workspace(
        organization_id=organization.id, actor_user_id="owner", workspace_id="ws-1"
    )
    remaining = await org_service.list_workspaces(organization.id)
    assert remaining == []
    assert any(entry.action == "organization.workspace_attached" for entry in audit_repo.entries)
    assert any(entry.action == "organization.workspace_detached" for entry in audit_repo.entries)
