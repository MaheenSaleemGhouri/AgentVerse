"""MCP integration domain entities — plain dataclasses, zero
framework/ORM imports (CLAUDE.md §5).

The model here is deliberately two-layered:

- `McpServer` is the **catalog**: a platform-wide definition of a server
  that *could* be installed. Global, not tenant-scoped.
- `InstalledServer` is a **workspace's installation** of one, or of its
  own custom endpoint.

Adding support for a new service is a catalog row, not a module. That is
the whole point of building on MCP rather than writing per-provider
connectors (ADR-0010).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class McpTransport(StrEnum):
    """How AgentVerse talks to a server.

    Transport follows the trust boundary and is **not** a free user
    choice: `STDIO` spawns a local process, so it is permitted only for
    vetted catalog entries whose command comes from the catalog row. A
    user-registered server is remote by definition and gets one of the
    HTTP transports, through the egress guard (ADR-0010).
    """

    #: Local co-located process. Catalog entries only, never user input.
    STDIO = "stdio"
    #: Remote server over Server-Sent Events.
    SSE = "sse"
    #: Remote server over MCP's streamable HTTP transport.
    STREAMABLE_HTTP = "streamable_http"


class McpAvailability(StrEnum):
    """Whether a server actually exists to install.

    Load-bearing for honesty. Seeding a service with no MCP server as
    installable produces a marketplace that lies — the user clicks
    Install and gets a connection that can never succeed. `CUSTOM_REQUIRED`
    says so on the card instead.
    """

    #: First-party server, maintained by the vendor.
    OFFICIAL = "official"
    #: Third-party server exists; quality is not vendor-backed.
    COMMUNITY = "community"
    #: No MCP server exists today — the user supplies their own endpoint.
    CUSTOM_REQUIRED = "custom_required"


class AuthScheme(StrEnum):
    """How a server authenticates AgentVerse."""

    NONE = "none"
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    BASIC = "basic"
    OAUTH2 = "oauth2"
    JWT = "jwt"
    CUSTOM_HEADER = "custom_header"


class InstallStatus(StrEnum):
    """Lifecycle of a workspace's installation.

    `DISABLED` is distinct from uninstalled: it stops the server's tools
    being offered without discarding its configuration and credentials,
    so re-enabling is not a re-setup.
    """

    PENDING_AUTH = "pending_auth"
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNREACHABLE = "unreachable"
    #: Never checked since installation.
    UNKNOWN = "unknown"


class PermissionLevel(StrEnum):
    """What an agent may do with a server's tools.

    Checked by AgentVerse before execution, independent of the model's
    judgment — a `READ_ONLY` grant makes a write tool uncallable no
    matter what an injected instruction argues (threat model T2).
    """

    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    ADMIN = "admin"


class ToolCallStatus(StrEnum):
    """Outcome of one tool call.

    `DENIED` is a first-class outcome, not an error: a blocked SSRF
    attempt that left no row would make the control unauditable, which is
    most of its value (ADR-0010).
    """

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    #: Rejected by the permission check or the egress guard.
    DENIED = "denied"
    #: The circuit breaker was open; the call was never attempted.
    CIRCUIT_OPEN = "circuit_open"
    #: Served from the result cache.
    CACHED = "cached"


@dataclass(frozen=True, slots=True)
class McpServerTool:
    """One tool a server advertises.

    `description` is attacker-controlled — a malicious server writes its
    own — and is treated as part of the prompt: size-capped, and shown to
    the user at install time before they confirm (threat model T4).
    """

    name: str
    description: str
    input_schema: dict[str, object]
    #: Whether calling this tool changes state on the remote system.
    #: Drives the `READ_ONLY` permission check.
    is_mutating: bool = False


@dataclass(frozen=True, slots=True)
class McpServer:
    """A catalog entry. Platform-global, deliberately not tenant-scoped.

    A table without `workspace_id` is normally a bug (CLAUDE.md §8); this
    is one of the explicit exceptions, called out in ADR-0010 so the
    exemption is a recorded decision rather than an omission.
    """

    id: str
    #: Stable machine name, e.g. "github". The marketplace URL slug.
    slug: str
    name: str
    description: str
    category: str
    transport: McpTransport
    availability: McpAvailability
    auth_scheme: AuthScheme
    #: Command + args for STDIO entries, from the catalog and never from
    #: user input. Null for HTTP transports.
    command: str | None = None
    command_args: list[str] = field(default_factory=list)
    #: Endpoint for HTTP transports. Null for STDIO.
    endpoint_url: str | None = None
    #: Credential keys the server needs, e.g. ["GITHUB_TOKEN"]. Shown on
    #: the install screen so the user knows what they are handing over.
    required_credentials: list[str] = field(default_factory=list)
    #: OAuth scopes requested, for `OAUTH2` entries.
    oauth_scopes: list[str] = field(default_factory=list)
    documentation_url: str | None = None
    icon_slug: str | None = None
    is_deprecated: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.min)
    updated_at: datetime = field(default_factory=lambda: datetime.min)

    @property
    def is_installable(self) -> bool:
        """Whether Install can do anything useful.

        A `CUSTOM_REQUIRED` entry is browsable and documented but has no
        endpoint to connect to until the user supplies one.
        """
        return self.availability is not McpAvailability.CUSTOM_REQUIRED and not self.is_deprecated


@dataclass(frozen=True, slots=True)
class InstalledServer:
    """A workspace's installation of a catalog entry, or its own custom
    server.

    `mcp_server_id` is null for a custom registration — the price of not
    duplicating the whole table for user-supplied endpoints.
    """

    id: str
    workspace_id: str
    mcp_server_id: str | None
    #: User-facing name; defaults to the catalog entry's but is editable,
    #: since a workspace may install the same server twice against
    #: different accounts.
    display_name: str
    transport: McpTransport
    #: Set only for custom servers; catalog installs read the catalog.
    endpoint_url: str | None
    status: InstallStatus
    health: HealthStatus
    #: Non-secret settings. Secrets live in `credentials`, encrypted —
    #: anything here is readable by every endpoint that returns a server.
    config: dict[str, object] = field(default_factory=dict)
    #: Tools discovered at the last successful discovery, cached so a run
    #: does not re-discover on every invocation.
    discovered_tools: list[McpServerTool] = field(default_factory=list)
    tools_discovered_at: datetime | None = None
    last_health_check_at: datetime | None = None
    last_error: str | None = None
    version: str | None = None
    installed_by_user_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.min)
    updated_at: datetime = field(default_factory=lambda: datetime.min)

    @property
    def is_usable(self) -> bool:
        return self.status is InstallStatus.ACTIVE and self.health is not HealthStatus.UNREACHABLE


@dataclass(frozen=True, slots=True)
class ServerVersion:
    """A recorded version of an installed server's tool surface.

    Kept so a breaking schema change on the server side surfaces as a
    detectable diff rather than a silent runtime failure (`mcp-expert`).
    """

    id: str
    workspace_id: str
    installed_server_id: str
    version: str
    tools: list[McpServerTool]
    #: Set when this version's tool surface differs from its predecessor.
    changed_tool_names: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.min)


@dataclass(frozen=True, slots=True)
class CredentialRef:
    """A stored credential, *without* its value.

    There is no field here for the plaintext and no read path in the API
    that returns one. Callers create, rotate, and delete; the boundary
    resolves the value at call time. Building the read path at all is
    what later gets loosened (ADR-0010).
    """

    id: str
    workspace_id: str
    installed_server_id: str
    #: Which credential this is, e.g. "GITHUB_TOKEN".
    key: str
    auth_scheme: AuthScheme
    #: Last four characters, for "is this the key I think it is?" — never
    #: a prefix, which would be a meaningful search key.
    hint: str
    expires_at: datetime | None = None
    last_rotated_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.min)


@dataclass(frozen=True, slots=True)
class IntegrationPermission:
    """A grant of an installed server's tools to an agent or a team.

    Exactly one of `agent_id`/`team_id` is set. A null pair means the
    grant is workspace-wide — every agent may use the server at this
    level, which is the coarse default a workspace admin opts into
    rather than the implicit one.
    """

    id: str
    workspace_id: str
    installed_server_id: str
    agent_id: str | None
    team_id: str | None
    level: PermissionLevel
    #: Empty means "every discovered tool at this level". A non-empty
    #: list narrows further, and maps to the SDK's own `ToolFilter`.
    allowed_tools: list[str] = field(default_factory=list)
    #: Per-call ceiling. Bounds a hung server's effect on a run.
    timeout_seconds: int = 30
    #: Retries on a transient failure, with backoff.
    max_retries: int = 2
    #: Cache TTL for identical calls; 0 disables caching.
    cache_ttl_seconds: int = 0
    #: Calls this grant permits per run. Bounds a tool loop.
    max_calls_per_run: int = 50
    #: Lower runs first when the model has several candidates.
    priority: int = 0
    granted_by_user_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.min)

    def permits(self, tool: McpServerTool) -> bool:
        """Whether this grant allows one tool.

        Checked by AgentVerse before execution and independent of the
        model's judgment (threat model T2).
        """
        if self.allowed_tools and tool.name not in self.allowed_tools:
            return False
        # A read-only grant makes a mutating tool uncallable, whatever an
        # injected instruction argues for.
        return not (tool.is_mutating and self.level is PermissionLevel.READ_ONLY)


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One tool invocation, recorded whether or not it ran.

    Separate from `agent_run_steps` because a tool call has arguments, a
    result, a target server, a credential reference, and a permission
    decision — none of which fit `payload` without making that column a
    union type. The trace UI joins them; the tables stay typed.
    """

    id: str
    workspace_id: str
    #: Null for a call made outside a run (a connection test).
    run_id: str | None
    team_session_id: str | None
    agent_id: str | None
    installed_server_id: str | None
    tool_name: str
    status: ToolCallStatus
    #: As the model supplied them, after schema validation.
    arguments: dict[str, object]
    #: Truncated to the output cap. The full result is never persisted —
    #: it is untrusted third-party content and an unbounded store of it
    #: is both a cost and a liability.
    result_preview: str | None
    result_bytes: int | None
    duration_ms: int | None
    error_message: str | None
    #: Why a `DENIED` call was denied — the permission rule or the egress
    #: rule that rejected it. Null otherwise.
    denial_reason: str | None
    attempt: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ToolMetric:
    """Rolled-up per-tool statistics for the runtime dashboard.

    Aggregated rather than computed from `tool_calls` on every dashboard
    load: that table is partitioned and high-volume, and a p95 over it
    per page view is a scan nobody needs.
    """

    id: str
    workspace_id: str
    installed_server_id: str
    tool_name: str
    bucket_start: datetime
    call_count: int
    error_count: int
    denied_count: int
    timeout_count: int
    total_duration_ms: int
    p95_duration_ms: int | None
