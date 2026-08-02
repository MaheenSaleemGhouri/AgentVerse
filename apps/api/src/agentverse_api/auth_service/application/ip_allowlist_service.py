"""Workspace IP allowlist use cases (Increment 7.4)."""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.entities import IpAllowlistEntry
from agentverse_api.auth_service.domain.exceptions import InvalidCidrError
from agentverse_api.auth_service.domain.ip_allowlist import is_ip_allowed, is_valid_cidr
from agentverse_api.auth_service.domain.ports import IpAllowlistRepository


@dataclass(slots=True)
class IpAllowlistService:
    entries: IpAllowlistRepository
    audit: AuditService

    async def list_entries(self, workspace_id: str) -> list[IpAllowlistEntry]:
        return await self.entries.list_for_workspace(workspace_id)

    async def add_entry(
        self, *, workspace_id: str, cidr: str, label: str | None, actor_user_id: str
    ) -> IpAllowlistEntry:
        if not is_valid_cidr(cidr):
            raise InvalidCidrError(cidr)

        entry = await self.entries.add(
            workspace_id=workspace_id,
            cidr=cidr,
            label=label,
            created_by_user_id=actor_user_id,
        )
        await self.audit.record(
            action="ip_allowlist.added",
            outcome="success",
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            target=cidr,
        )
        return entry

    async def remove_entry(
        self, *, workspace_id: str, entry_id: str, actor_user_id: str
    ) -> None:
        await self.entries.remove_by_id(workspace_id=workspace_id, entry_id=entry_id)
        await self.audit.record(
            action="ip_allowlist.removed",
            outcome="success",
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            target=entry_id,
        )

    async def is_allowed(self, *, workspace_id: str, client_ip: str | None) -> bool:
        entries = await self.entries.list_for_workspace(workspace_id)
        return is_ip_allowed(client_ip, [entry.cidr for entry in entries])
