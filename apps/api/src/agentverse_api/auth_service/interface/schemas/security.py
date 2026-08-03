"""Request/response schemas for the Security Center."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from agentverse_api.auth_service.domain.security import SecurityEventType, SecuritySeverity


class SecurityEventResponse(BaseModel):
    id: str
    user_id: str | None
    workspace_id: str | None
    organization_id: str | None
    event_type: SecurityEventType
    severity: SecuritySeverity
    ip_address: str | None
    user_agent: str | None
    metadata: dict[str, str]
    created_at: datetime


class TrustedDeviceResponse(BaseModel):
    id: str
    device_fingerprint: str
    device_name: str | None
    user_agent: str | None
    ip_address: str | None
    trusted_at: datetime
    last_seen_at: datetime
    revoked_at: datetime | None


class TrustDeviceRequest(BaseModel):
    #: Opaque to the server. Long enough to be collision-resistant,
    #: capped so it can never be used as unbounded storage.
    device_fingerprint: str = Field(min_length=8, max_length=256)
    device_name: str | None = Field(default=None, max_length=120)


class PasswordPolicyResponse(BaseModel):
    min_length: int
    require_uppercase: bool
    require_lowercase: bool
    require_number: bool
    require_symbol: bool
    max_age_days: int | None
    #: False means no policy row exists and the platform default is in
    #: force. The UI must not present a default as a deliberate choice.
    is_configured: bool


class UpdatePasswordPolicyRequest(BaseModel):
    # Floors at 8 to match the table's CHECK constraint: a "policy" that
    # weakens the platform baseline is not a setting worth offering.
    min_length: int = Field(ge=8, le=128)
    require_uppercase: bool
    require_lowercase: bool
    require_number: bool
    require_symbol: bool
    max_age_days: int | None = Field(default=None, ge=1, le=3650)


class CheckPasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=512)


class CheckPasswordResponse(BaseModel):
    #: Empty means the password satisfies the policy. Every violation is
    #: returned at once so the user is not made to discover the rules one
    #: retry at a time.
    violations: list[str]


class ScoreFactorResponse(BaseModel):
    key: str
    label: str
    earned: int
    possible: int
    remediation: str | None


class SecurityScoreResponse(BaseModel):
    score: int
    grade: str
    factors: list[ScoreFactorResponse]
