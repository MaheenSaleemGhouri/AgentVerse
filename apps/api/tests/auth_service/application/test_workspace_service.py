import pytest

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.application.workspace_service import WorkspaceService
from agentverse_api.auth_service.domain.exceptions import (
    LastOwnerError,
    UserAlreadyMemberError,
    WorkspaceSlugTakenError,
)
from agentverse_api.auth_service.domain.role import Role
from tests.fakes.auth_service_repositories import FakeAuditLogRepository, FakeWorkspaceRepository


@pytest.fixture
def service() -> tuple[WorkspaceService, FakeAuditLogRepository]:
    audit_repo = FakeAuditLogRepository()
    workspace_repo = FakeWorkspaceRepository()
    return (
        WorkspaceService(workspaces=workspace_repo, audit=AuditService(audit_logs=audit_repo)),
        audit_repo,
    )


async def test_create_workspace_makes_creator_owner(
    service: tuple[WorkspaceService, FakeAuditLogRepository],
) -> None:
    workspace_service, audit_repo = service

    workspace = await workspace_service.create_workspace(name="Acme Inc.", owner_user_id="u1")

    membership = await workspace_service.workspaces.get_membership(
        workspace_id=workspace.id, user_id="u1"
    )
    assert membership is not None
    assert membership.role is Role.OWNER
    assert any(entry.action == "workspace.created" for entry in audit_repo.entries)


async def test_create_workspace_resolves_slug_collision(
    service: tuple[WorkspaceService, FakeAuditLogRepository],
) -> None:
    workspace_service, _ = service

    first = await workspace_service.create_workspace(name="Acme", owner_user_id="u1")
    second = await workspace_service.create_workspace(name="Acme", owner_user_id="u2")

    assert first.slug == "acme"
    assert second.slug == "acme-2"


async def test_create_workspace_raises_when_all_ten_slug_candidates_taken(
    service: tuple[WorkspaceService, FakeAuditLogRepository],
) -> None:
    workspace_service, _ = service
    for i in range(10):
        await workspace_service.create_workspace(name="Acme", owner_user_id=f"u{i}")

    with pytest.raises(WorkspaceSlugTakenError):
        await workspace_service.create_workspace(name="Acme", owner_user_id="u-overflow")


async def test_invite_member_adds_membership_and_audits(
    service: tuple[WorkspaceService, FakeAuditLogRepository],
) -> None:
    workspace_service, audit_repo = service
    workspace = await workspace_service.create_workspace(name="Acme", owner_user_id="owner")

    member = await workspace_service.invite_member(
        workspace_id=workspace.id,
        inviter_user_id="owner",
        invitee_user_id="new-user",
        role=Role.MEMBER,
    )

    assert member.role is Role.MEMBER
    assert any(entry.action == "member.invited" for entry in audit_repo.entries)


async def test_invite_member_rejects_existing_member(
    service: tuple[WorkspaceService, FakeAuditLogRepository],
) -> None:
    workspace_service, _ = service
    workspace = await workspace_service.create_workspace(name="Acme", owner_user_id="owner")
    await workspace_service.invite_member(
        workspace_id=workspace.id, inviter_user_id="owner", invitee_user_id="dup", role=Role.MEMBER
    )

    with pytest.raises(UserAlreadyMemberError):
        await workspace_service.invite_member(
            workspace_id=workspace.id,
            inviter_user_id="owner",
            invitee_user_id="dup",
            role=Role.VIEWER,
        )


async def test_change_member_role_updates_role(
    service: tuple[WorkspaceService, FakeAuditLogRepository],
) -> None:
    workspace_service, audit_repo = service
    workspace = await workspace_service.create_workspace(name="Acme", owner_user_id="owner")
    await workspace_service.invite_member(
        workspace_id=workspace.id, inviter_user_id="owner", invitee_user_id="u2", role=Role.MEMBER
    )

    updated = await workspace_service.change_member_role(
        workspace_id=workspace.id, actor_user_id="owner", target_user_id="u2", new_role=Role.ADMIN
    )

    assert updated.role is Role.ADMIN
    assert any(entry.action == "member.role_changed" for entry in audit_repo.entries)


async def test_change_member_role_blocks_demoting_the_last_owner(
    service: tuple[WorkspaceService, FakeAuditLogRepository],
) -> None:
    """The one workspace-integrity invariant this service must enforce:
    a workspace can never end up with zero owners (docs/roadmap.md Phase 1)."""
    workspace_service, _ = service
    workspace = await workspace_service.create_workspace(name="Acme", owner_user_id="sole-owner")

    with pytest.raises(LastOwnerError):
        await workspace_service.change_member_role(
            workspace_id=workspace.id,
            actor_user_id="sole-owner",
            target_user_id="sole-owner",
            new_role=Role.ADMIN,
        )


async def test_change_member_role_allows_demotion_when_another_owner_exists(
    service: tuple[WorkspaceService, FakeAuditLogRepository],
) -> None:
    workspace_service, _ = service
    workspace = await workspace_service.create_workspace(name="Acme", owner_user_id="owner1")
    await workspace_service.invite_member(
        workspace_id=workspace.id,
        inviter_user_id="owner1",
        invitee_user_id="owner2",
        role=Role.OWNER,
    )

    updated = await workspace_service.change_member_role(
        workspace_id=workspace.id,
        actor_user_id="owner2",
        target_user_id="owner1",
        new_role=Role.ADMIN,
    )

    assert updated.role is Role.ADMIN


async def test_remove_member_blocks_removing_the_last_owner(
    service: tuple[WorkspaceService, FakeAuditLogRepository],
) -> None:
    workspace_service, _ = service
    workspace = await workspace_service.create_workspace(name="Acme", owner_user_id="sole-owner")

    with pytest.raises(LastOwnerError):
        await workspace_service.remove_member(
            workspace_id=workspace.id, actor_user_id="sole-owner", target_user_id="sole-owner"
        )


async def test_remove_member_succeeds_for_non_owner(
    service: tuple[WorkspaceService, FakeAuditLogRepository],
) -> None:
    workspace_service, audit_repo = service
    workspace = await workspace_service.create_workspace(name="Acme", owner_user_id="owner")
    await workspace_service.invite_member(
        workspace_id=workspace.id, inviter_user_id="owner", invitee_user_id="u2", role=Role.MEMBER
    )

    await workspace_service.remove_member(
        workspace_id=workspace.id, actor_user_id="owner", target_user_id="u2"
    )

    remaining = await workspace_service.list_members(workspace.id)
    assert all(member.user_id != "u2" for member in remaining)
    assert any(entry.action == "member.removed" for entry in audit_repo.entries)
