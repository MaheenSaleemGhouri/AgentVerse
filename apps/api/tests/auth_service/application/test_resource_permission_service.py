from __future__ import annotations

import pytest

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.application.resource_permission_service import (
    ResourcePermissionService,
)
from tests.fakes.auth_service_repositories import (
    FakeAuditLogRepository,
    FakeResourcePermissionRepository,
)


@pytest.fixture
def service() -> tuple[ResourcePermissionService, FakeAuditLogRepository]:
    audit_repo = FakeAuditLogRepository()
    return (
        ResourcePermissionService(
            resource_permissions=FakeResourcePermissionRepository(),
            audit=AuditService(audit_logs=audit_repo),
        ),
        audit_repo,
    )


async def test_grant_creates_a_row_and_is_audited(
    service: tuple[ResourcePermissionService, FakeAuditLogRepository],
) -> None:
    rp_service, audit_repo = service

    grant = await rp_service.grant(
        workspace_id="ws-1",
        resource_type="billing",
        resource_id="",
        principal_id="member-1",
        permission="manage",
        granted_by_user_id="owner-1",
    )

    assert grant.principal_type == "user"
    assert grant.permission == "manage"
    assert any(entry.action == "resource_permission.granted" for entry in audit_repo.entries)


async def test_granting_the_same_tuple_twice_updates_rather_than_duplicates(
    service: tuple[ResourcePermissionService, FakeAuditLogRepository],
) -> None:
    rp_service, _ = service

    first = await rp_service.grant(
        workspace_id="ws-1",
        resource_type="billing",
        resource_id="",
        principal_id="member-1",
        permission="manage",
        granted_by_user_id="owner-1",
    )
    second = await rp_service.grant(
        workspace_id="ws-1",
        resource_type="billing",
        resource_id="",
        principal_id="member-1",
        permission="manage",
        granted_by_user_id="owner-2",
    )

    assert first.id == second.id
    assert second.granted_by_user_id == "owner-2"
    remaining = await rp_service.list_for_workspace("ws-1")
    assert len(remaining) == 1


async def test_revoke_removes_the_grant_and_is_audited(
    service: tuple[ResourcePermissionService, FakeAuditLogRepository],
) -> None:
    rp_service, audit_repo = service
    grant = await rp_service.grant(
        workspace_id="ws-1",
        resource_type="billing",
        resource_id="",
        principal_id="member-1",
        permission="manage",
        granted_by_user_id="owner-1",
    )

    await rp_service.revoke(workspace_id="ws-1", permission_id=grant.id, actor_user_id="owner-1")

    assert await rp_service.list_for_workspace("ws-1") == []
    assert any(entry.action == "resource_permission.revoked" for entry in audit_repo.entries)


async def test_revoke_does_not_remove_a_grant_from_a_different_workspace(
    service: tuple[ResourcePermissionService, FakeAuditLogRepository],
) -> None:
    rp_service, _ = service
    grant = await rp_service.grant(
        workspace_id="ws-1",
        resource_type="billing",
        resource_id="",
        principal_id="member-1",
        permission="manage",
        granted_by_user_id="owner-1",
    )

    await rp_service.revoke(workspace_id="ws-2", permission_id=grant.id, actor_user_id="intruder")

    remaining = await rp_service.list_for_workspace("ws-1")
    assert len(remaining) == 1
