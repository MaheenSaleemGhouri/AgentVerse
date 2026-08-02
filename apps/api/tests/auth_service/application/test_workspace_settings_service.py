from __future__ import annotations

import pytest

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.application.workspace_settings_service import (
    WorkspaceSettingsService,
)
from tests.fakes.auth_service_repositories import (
    FakeAuditLogRepository,
    FakeWorkspaceSettingsRepository,
)


@pytest.fixture
def service() -> tuple[WorkspaceSettingsService, FakeAuditLogRepository]:
    audit_repo = FakeAuditLogRepository()
    settings_repo = FakeWorkspaceSettingsRepository()
    return (
        WorkspaceSettingsService(settings=settings_repo, audit=AuditService(audit_logs=audit_repo)),
        audit_repo,
    )


async def test_get_settings_returns_none_when_no_row_exists(
    service: tuple[WorkspaceSettingsService, FakeAuditLogRepository],
) -> None:
    settings_service, _ = service

    result = await settings_service.get_settings("ws-1")

    assert result is None


async def test_update_settings_creates_and_is_audited(
    service: tuple[WorkspaceSettingsService, FakeAuditLogRepository],
) -> None:
    settings_service, audit_repo = service

    updated = await settings_service.update_settings(
        workspace_id="ws-1",
        actor_user_id="u1",
        logo_url="https://example.com/logo.png",
        brand_color="#111111",
        custom_domain="acme.example.com",
        retention_days=90,
        storage_limit_mb=1024,
    )

    assert updated.workspace_id == "ws-1"
    assert updated.retention_days == 90

    fetched = await settings_service.get_settings("ws-1")
    assert fetched == updated
    assert any(entry.action == "workspace.settings_updated" for entry in audit_repo.entries)


async def test_update_settings_a_second_time_overwrites_the_same_row(
    service: tuple[WorkspaceSettingsService, FakeAuditLogRepository],
) -> None:
    settings_service, _ = service

    await settings_service.update_settings(
        workspace_id="ws-1",
        actor_user_id="u1",
        logo_url=None,
        brand_color=None,
        custom_domain=None,
        retention_days=30,
        storage_limit_mb=None,
    )
    await settings_service.update_settings(
        workspace_id="ws-1",
        actor_user_id="u2",
        logo_url=None,
        brand_color=None,
        custom_domain=None,
        retention_days=60,
        storage_limit_mb=None,
    )

    fetched = await settings_service.get_settings("ws-1")
    assert fetched is not None
    assert fetched.retention_days == 60
    assert fetched.updated_by_user_id == "u2"
