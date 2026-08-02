"""Request/response schemas for the audit-log read API (CLAUDE.md §7)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: str
    workspace_id: str | None
    actor_user_id: str | None
    action: str
    target: str | None
    outcome: str
    metadata: dict[str, str]
    created_at: datetime


class AuditLogPage(BaseModel):
    data: list[AuditLogResponse]
    next_cursor: str | None
    has_more: bool
