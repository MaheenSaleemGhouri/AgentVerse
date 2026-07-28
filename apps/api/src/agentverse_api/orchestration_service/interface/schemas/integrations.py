"""Request/response models for the MCP integration API.

**No response model here has a field for a credential value.** Not
masked, not truncated, not `"sk-...abcd"`. `CredentialResponse` carries a
four-character tail and metadata. There is deliberately no schema that
could serialise a secret, so no future endpoint can accidentally do it
(ADR-0010).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

TransportLiteral = Literal["stdio", "sse", "streamable_http"]
AvailabilityLiteral = Literal["official", "community", "custom_required"]
AuthSchemeLiteral = Literal[
    "none", "api_key", "bearer_token", "basic", "oauth2", "jwt", "custom_header"
]
InstallStatusLiteral = Literal["pending_auth", "active", "disabled", "error"]
HealthLiteral = Literal["healthy", "degraded", "unreachable", "unknown"]
PermissionLevelLiteral = Literal["read_only", "read_write", "admin"]
ToolCallStatusLiteral = Literal["success", "error", "timeout", "denied", "circuit_open", "cached"]

#: A user-registered server's endpoint. Capped because it is stored,
#: rendered, and passed to the egress guard; an unbounded URL is a
#: denial-of-service on every one of those.
MAX_URL_LENGTH = 2000


class McpServerResponse(BaseModel):
    """A marketplace catalog entry."""

    id: str
    slug: str
    name: str
    description: str
    category: str
    transport: TransportLiteral
    availability: AvailabilityLiteral
    auth_scheme: AuthSchemeLiteral
    #: What the user will be asked for at install time, shown *before*
    #: they confirm rather than after.
    required_credentials: list[str]
    oauth_scopes: list[str]
    documentation_url: str | None
    icon_slug: str | None
    #: False for `custom_required` entries. The UI disables Install and
    #: shows the reason rather than offering a button that leads to a
    #: connection which can never succeed.
    is_installable: bool


class ToolSummary(BaseModel):
    name: str
    description: str
    #: Whether calling this tool changes state on the remote system.
    #: Inferred, not declared — MCP has no such flag — and biased toward
    #: `true` for anything unrecognised.
    is_mutating: bool


class InstalledServerResponse(BaseModel):
    id: str
    workspace_id: str
    mcp_server_id: str | None
    display_name: str
    transport: TransportLiteral
    endpoint_url: str | None
    status: InstallStatusLiteral
    health: HealthLiteral
    tools: list[ToolSummary]
    tools_discovered_at: datetime | None
    last_health_check_at: datetime | None
    last_error: str | None
    version: str | None
    created_at: datetime
    updated_at: datetime


class InstallFromCatalogRequest(BaseModel):
    """Installing a vetted catalog entry.

    Deliberately carries no command, no args, and no endpoint: all three
    come from the catalog row. Accepting them here would let a caller
    turn a vetted stdio entry into an arbitrary local command (ADR-0010).
    """

    mcp_server_id: str = Field(min_length=1, max_length=64)
    #: Optional override — a workspace may install the same server twice
    #: against different accounts and needs to tell them apart.
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    config: dict[str, Any] = Field(default_factory=dict)


class RegisterCustomServerRequest(BaseModel):
    """Registering a user's own MCP server.

    No `transport` field for stdio: a custom server is remote by
    definition and gets an HTTP transport. The literal below excludes
    stdio at the type level rather than validating it away, so the
    refusal is visible in the generated contract.
    """

    display_name: str = Field(min_length=1, max_length=200)
    transport: Literal["sse", "streamable_http"]
    endpoint_url: str = Field(min_length=1, max_length=MAX_URL_LENGTH)
    auth_scheme: AuthSchemeLiteral = "none"
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("endpoint_url")
    @classmethod
    def _must_be_http(cls, value: str) -> str:
        """A cheap first check, not the control.

        The egress guard is what actually decides — it resolves the host
        and validates every address. This exists so an obviously wrong
        scheme fails at the form rather than after a round trip.
        """
        if not value.startswith(("http://", "https://")):
            raise ValueError("endpoint_url must be an http:// or https:// URL")
        return value


class UpdateInstalledServerRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    #: `disabled` stops the server's tools being offered without
    #: discarding its configuration and credentials, so re-enabling is
    #: not a re-setup.
    status: Literal["active", "disabled"] | None = None
    config: dict[str, Any] | None = None


class PutCredentialRequest(BaseModel):
    """Writing or rotating a credential.

    One shape for both: a rotation is a write of the same thing, and a
    separate rotate endpoint would be a second path to keep correct.
    """

    key: str = Field(min_length=1, max_length=200)
    #: Write-only: encrypted before it reaches the database, and no
    #: endpoint returns it. Kept out of logs by never logging a request
    #: body rather than by a field flag — Pydantic's `repr` is
    #: field-specific metadata that `Field()` cannot attach here, so
    #: relying on it would be a control that silently does nothing.
    value: str = Field(min_length=1, max_length=8000)
    auth_scheme: AuthSchemeLiteral
    expires_at: datetime | None = None


class CredentialResponse(BaseModel):
    """Metadata about a stored credential. Never its value.

    `hint` is the last four characters — never a prefix, because many
    credential formats put a recognisable low-entropy prefix at the front
    (`sk-`, `ghp_`, `xoxb-`) which identifies the key's kind and issuer.
    """

    id: str
    installed_server_id: str
    key: str
    auth_scheme: AuthSchemeLiteral
    hint: str
    expires_at: datetime | None
    last_rotated_at: datetime | None
    created_at: datetime


class GrantPermissionRequest(BaseModel):
    """Granting a server's tools to an agent, a team, or the workspace.

    At most one subject. Both set is rejected here as well as by the
    table's CHECK constraint — the DB is the guarantee, this is the
    readable error.
    """

    agent_id: str | None = Field(default=None, max_length=64)
    team_id: str | None = Field(default=None, max_length=64)
    level: PermissionLevelLiteral = "read_only"
    #: Empty means every discovered tool at this level. A non-empty list
    #: narrows further and maps to the SDK's own `ToolFilter`.
    allowed_tools: list[str] = Field(default_factory=list, max_length=100)
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    max_retries: int = Field(default=2, ge=0, le=5)
    cache_ttl_seconds: int = Field(default=0, ge=0, le=86_400)
    max_calls_per_run: int = Field(default=50, ge=1, le=500)
    priority: int = Field(default=0, ge=0, le=100)

    @field_validator("team_id")
    @classmethod
    def _at_most_one_subject(cls, value: str | None, info: Any) -> str | None:
        if value and info.data.get("agent_id"):
            raise ValueError("set agent_id or team_id, not both")
        return value


class PermissionResponse(BaseModel):
    id: str
    installed_server_id: str
    agent_id: str | None
    team_id: str | None
    level: PermissionLevelLiteral
    allowed_tools: list[str]
    timeout_seconds: int
    max_retries: int
    cache_ttl_seconds: int
    max_calls_per_run: int
    priority: int
    created_at: datetime


class ToolCallResponse(BaseModel):
    id: str
    run_id: str | None
    agent_id: str | None
    installed_server_id: str | None
    tool_name: str
    status: ToolCallStatusLiteral
    arguments: dict[str, Any]
    #: Truncated. The full result is untrusted third-party content and an
    #: unbounded store of it is a liability, not an archive.
    result_preview: str | None
    result_bytes: int | None
    duration_ms: int | None
    error_message: str | None
    #: Which rule rejected a denied call — the permission rule or the
    #: egress rule. This is the audit trail for a blocked SSRF attempt.
    denial_reason: str | None
    attempt: int
    created_at: datetime


class ToolCallPage(BaseModel):
    data: list[ToolCallResponse]
    next_cursor: str | None
    has_more: bool


class IntegrationMetricsResponse(BaseModel):
    total_calls: int
    succeeded_calls: int
    failed_calls: int
    #: Non-zero here is the signal worth alerting on: an agent repeatedly
    #: attempting something it is not permitted to do.
    denied_calls: int
    timed_out_calls: int
    cached_calls: int
    p95_duration_ms: int
    average_duration_ms: int


class HealthCheckResponse(BaseModel):
    installed_server_id: str
    health: HealthLiteral
    tool_count: int
    latency_ms: int | None
    error: str | None
    checked_at: datetime


class OauthStartResponse(BaseModel):
    """Where to send the user to authorise.

    The `state` is returned so a client can correlate the callback, but
    it is the *server's* copy in `oauth_sessions` that is authoritative —
    a client-supplied state would be an open redirect waiting to happen.
    """

    authorization_url: str
    state: str
    expires_at: datetime
