from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from agentverse_api.auth_service.domain.api_key_scope import ApiKeyScope


class IssueApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scope: ApiKeyScope = ApiKeyScope.FULL
    tier: str = Field(default="standard", max_length=50)


class ApiKeyResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    scope: ApiKeyScope
    tier: str
    rotated_from_id: str | None


class IssuedApiKeyResponse(ApiKeyResponse):
    # Shown exactly once, at issuance (CLAUDE.md §10). Never returned by
    # any other endpoint — list/get responses use ApiKeyResponse, which
    # has no plaintext field at all.
    key: str
