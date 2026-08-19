from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from agentverse_api.auth_service.domain.api_key_scope import ApiKeyScope


class IssueMcpClientRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    #: `READ_ONLY` caps every MCP tool call at `viewer` (list/get tools
    #: only — `run_agent`/`run_workflow` are refused); `FULL` allows
    #: whatever the issuer's own current role permits, same ceiling
    #: logic `api_keys.scope` already computes for the REST API.
    scope: ApiKeyScope = ApiKeyScope.FULL
    #: A lifetime, not an absolute timestamp — same reasoning as
    #: `IssueApiKeyRequest.expires_in_days`.
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class McpClientResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    scope: ApiKeyScope
    expires_at: datetime | None
    use_count: int


class IssuedMcpClientResponse(McpClientResponse):
    # Shown exactly once, at issuance — same posture as `IssuedApiKeyResponse`.
    key: str
