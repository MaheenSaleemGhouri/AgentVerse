"""In-memory stand-in for `AuditService` — used by route-level unit
tests that override `get_db_session`-adjacent dependencies with fakes
and must not open a real Postgres connection just because a route now
also audits its own action (CLAUDE.md §11).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from agentverse_api.auth_service.domain.entities import AuditLogEntry


@dataclass
class FakeAuditService:
    recorded: list[AuditLogEntry] = field(default_factory=list)

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
        entry = AuditLogEntry(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            target=target,
            outcome=outcome,
            metadata=metadata or {},
            created_at=datetime.now(UTC),
            organization_id=organization_id,
        )
        self.recorded.append(entry)
        return entry
