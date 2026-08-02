"""Request/response schemas for the workspace IP allowlist (CLAUDE.md §7)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AddIpAllowlistEntryRequest(BaseModel):
    #: Shape-checked here; parsed for real by `domain.ip_allowlist.is_valid_cidr`
    #: in the service layer, which is the single source of truth for what
    #: counts as a valid range.
    cidr: str = Field(min_length=1, max_length=64)
    label: str | None = Field(default=None, max_length=100)


class IpAllowlistEntryResponse(BaseModel):
    id: str
    workspace_id: str
    cidr: str
    label: str | None
    created_by_user_id: str
    created_at: datetime
