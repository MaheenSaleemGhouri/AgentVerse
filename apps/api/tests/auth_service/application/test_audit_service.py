from __future__ import annotations

import pytest

from agentverse_api.auth_service.application.audit_service import AuditService
from tests.fakes.auth_service_repositories import FakeAuditLogRepository


@pytest.fixture
def service() -> tuple[AuditService, FakeAuditLogRepository]:
    audit_repo = FakeAuditLogRepository()
    return AuditService(audit_logs=audit_repo), audit_repo


async def test_list_for_workspace_only_returns_that_workspaces_entries(
    service: tuple[AuditService, FakeAuditLogRepository],
) -> None:
    audit_service, _ = service
    await audit_service.record(action="workspace.created", outcome="success", workspace_id="ws-1")
    await audit_service.record(action="workspace.created", outcome="success", workspace_id="ws-2")

    page = await audit_service.list_for_workspace(workspace_id="ws-1", limit=10)

    assert len(page) == 1
    assert page[0].workspace_id == "ws-1"


async def test_list_for_workspace_filters_by_action_and_actor(
    service: tuple[AuditService, FakeAuditLogRepository],
) -> None:
    audit_service, _ = service
    await audit_service.record(
        action="permission.denied", outcome="denied", workspace_id="ws-1", actor_user_id="u1"
    )
    await audit_service.record(
        action="workspace.created", outcome="success", workspace_id="ws-1", actor_user_id="u1"
    )
    await audit_service.record(
        action="permission.denied", outcome="denied", workspace_id="ws-1", actor_user_id="u2"
    )

    by_action = await audit_service.list_for_workspace(
        workspace_id="ws-1", limit=10, action="permission.denied"
    )
    assert {entry.actor_user_id for entry in by_action} == {"u1", "u2"}

    by_actor = await audit_service.list_for_workspace(
        workspace_id="ws-1", limit=10, actor_user_id="u2"
    )
    assert len(by_actor) == 1
    assert by_actor[0].action == "permission.denied"


async def test_list_for_workspace_orders_newest_first_and_respects_limit(
    service: tuple[AuditService, FakeAuditLogRepository],
) -> None:
    audit_service, _ = service
    for i in range(5):
        await audit_service.record(action=f"event.{i}", outcome="success", workspace_id="ws-1")

    page = await audit_service.list_for_workspace(workspace_id="ws-1", limit=3)

    assert len(page) == 3
    assert [entry.action for entry in page] == ["event.4", "event.3", "event.2"]


async def test_list_for_workspace_cursor_excludes_entries_at_or_after_it(
    service: tuple[AuditService, FakeAuditLogRepository],
) -> None:
    audit_service, _ = service
    entries = [
        await audit_service.record(action=f"event.{i}", outcome="success", workspace_id="ws-1")
        for i in range(3)
    ]

    page = await audit_service.list_for_workspace(
        workspace_id="ws-1", limit=10, cursor=entries[2].created_at.isoformat()
    )

    assert [entry.action for entry in page] == ["event.1", "event.0"]
