"""Audit logging use case — the single call site every other use case
and `require_role`'s denial path goes through, so `audit_logs` coverage
can't be silently skipped by a future route author (ADR-0004).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from agentverse_api.auth_service.domain.entities import AuditLogEntry
from agentverse_api.auth_service.domain.ports import AuditLogRepository


@dataclass(slots=True)
class AuditService:
    audit_logs: AuditLogRepository

    async def record(
        self,
        *,
        action: str,
        outcome: str,
        workspace_id: str | None = None,
        actor_user_id: str | None = None,
        target: str | None = None,
        metadata: dict[str, str] | None = None,
        organization_id: str | None = None,
    ) -> AuditLogEntry:
        return await self.audit_logs.record(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            target=target,
            outcome=outcome,
            metadata=metadata or {},
            organization_id=organization_id,
        )

    async def list_for_workspace(
        self,
        *,
        workspace_id: str,
        limit: int,
        cursor: str | None = None,
        action: str | None = None,
        actor_user_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[AuditLogEntry]:
        return await self.audit_logs.list_for_workspace(
            workspace_id=workspace_id,
            limit=limit,
            cursor=cursor,
            action=action,
            actor_user_id=actor_user_id,
            since=since,
            until=until,
        )
