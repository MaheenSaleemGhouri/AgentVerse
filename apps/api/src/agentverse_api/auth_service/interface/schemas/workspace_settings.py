"""Request/response schemas for workspace-wide settings (CLAUDE.md §7).

`WorkspaceSettingsResponse.updated_at` is nullable — `None` means no
settings row exists yet (every pre-existing workspace), distinct from a
row that happens to have every field cleared.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class WorkspaceSettingsResponse(BaseModel):
    workspace_id: str
    logo_url: str | None
    brand_color: str | None
    custom_domain: str | None
    retention_days: int | None
    storage_limit_mb: int | None
    updated_at: datetime | None
    updated_by_user_id: str | None


class UpdateWorkspaceSettingsRequest(BaseModel):
    logo_url: str | None = Field(default=None, max_length=2048)
    brand_color: str | None = Field(default=None, max_length=32)
    custom_domain: str | None = Field(default=None, max_length=255)
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    storage_limit_mb: int | None = Field(default=None, ge=1)
