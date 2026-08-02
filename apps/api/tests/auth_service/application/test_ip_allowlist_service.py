from __future__ import annotations

import pytest

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.application.ip_allowlist_service import IpAllowlistService
from agentverse_api.auth_service.domain.exceptions import InvalidCidrError
from tests.fakes.auth_service_repositories import (
    FakeAuditLogRepository,
    FakeIpAllowlistRepository,
)


@pytest.fixture
def service() -> tuple[IpAllowlistService, FakeAuditLogRepository]:
    audit_repo = FakeAuditLogRepository()
    return (
        IpAllowlistService(
            entries=FakeIpAllowlistRepository(), audit=AuditService(audit_logs=audit_repo)
        ),
        audit_repo,
    )


async def test_add_entry_stores_and_audits(
    service: tuple[IpAllowlistService, FakeAuditLogRepository],
) -> None:
    ip_service, audit_repo = service

    entry = await ip_service.add_entry(
        workspace_id="ws-1", cidr="10.0.0.0/8", label="Office", actor_user_id="owner"
    )

    assert entry.cidr == "10.0.0.0/8"
    assert any(e.action == "ip_allowlist.added" for e in audit_repo.entries)


async def test_add_entry_rejects_a_malformed_cidr(
    service: tuple[IpAllowlistService, FakeAuditLogRepository],
) -> None:
    ip_service, _ = service

    with pytest.raises(InvalidCidrError):
        await ip_service.add_entry(
            workspace_id="ws-1", cidr="not-an-ip", label=None, actor_user_id="owner"
        )


async def test_a_workspace_with_no_entries_allows_every_ip(
    service: tuple[IpAllowlistService, FakeAuditLogRepository],
) -> None:
    """The invariant that keeps every pre-existing workspace unaffected."""
    ip_service, _ = service

    assert await ip_service.is_allowed(workspace_id="ws-untouched", client_ip="203.0.113.9")


async def test_a_restricted_workspace_allows_inside_and_denies_outside(
    service: tuple[IpAllowlistService, FakeAuditLogRepository],
) -> None:
    ip_service, _ = service
    await ip_service.add_entry(
        workspace_id="ws-1", cidr="10.0.0.0/8", label=None, actor_user_id="owner"
    )

    assert await ip_service.is_allowed(workspace_id="ws-1", client_ip="10.1.2.3")
    assert not await ip_service.is_allowed(workspace_id="ws-1", client_ip="203.0.113.9")
    # A different workspace has its own (empty) allowlist — restricting
    # one workspace must never restrict another.
    assert await ip_service.is_allowed(workspace_id="ws-2", client_ip="203.0.113.9")


async def test_remove_entry_reopens_the_workspace_and_is_audited(
    service: tuple[IpAllowlistService, FakeAuditLogRepository],
) -> None:
    ip_service, audit_repo = service
    entry = await ip_service.add_entry(
        workspace_id="ws-1", cidr="10.0.0.0/8", label=None, actor_user_id="owner"
    )
    assert not await ip_service.is_allowed(workspace_id="ws-1", client_ip="203.0.113.9")

    await ip_service.remove_entry(
        workspace_id="ws-1", entry_id=entry.id, actor_user_id="owner"
    )

    assert await ip_service.is_allowed(workspace_id="ws-1", client_ip="203.0.113.9")
    assert any(e.action == "ip_allowlist.removed" for e in audit_repo.entries)


async def test_remove_entry_does_not_remove_another_workspaces_entry(
    service: tuple[IpAllowlistService, FakeAuditLogRepository],
) -> None:
    ip_service, _ = service
    entry = await ip_service.add_entry(
        workspace_id="ws-1", cidr="10.0.0.0/8", label=None, actor_user_id="owner"
    )

    await ip_service.remove_entry(
        workspace_id="ws-2", entry_id=entry.id, actor_user_id="intruder"
    )

    assert len(await ip_service.list_entries("ws-1")) == 1
