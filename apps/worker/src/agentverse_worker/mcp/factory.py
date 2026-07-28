"""Builds SDK `MCPServer` objects from stored installations.

AgentVerse writes no MCP protocol code. The SDK ships `MCPServerStdio`,
`MCPServerSse`, and `MCPServerStreamableHttp`, and all three are used
directly — this module only decides *which* to construct and *with what*
(ADR-0010).

What AgentVerse contributes is everything the SDK has no notion of:

- which transport an installation is *allowed* to use,
- where its credentials come from and how they reach the wire,
- that every HTTP hop goes through the egress guard,
- which tools the calling agent may see at all.

The last one uses the SDK's own `ToolFilter` rather than a hand-written
filter, so an agent's allowed-tool list is enforced by the same code path
the SDK uses for everything else.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agentverse_shared.security.egress_guard import EgressDeniedError, validate_destination

from agents.mcp import (
    MCPServer,
    MCPServerSse,
    MCPServerSseParams,
    MCPServerStdio,
    MCPServerStdioParams,
    MCPServerStreamableHttp,
    MCPServerStreamableHttpParams,
    create_static_tool_filter,
)
from agentverse_worker.mcp.transport import guarded_http_client_factory

logger = logging.getLogger(__name__)

#: How long the SDK may wait on a single MCP client session operation.
#: Deliberately short — a hung server must not consume a run's whole
#: wall-clock budget before the boundary's own timeout notices.
CLIENT_SESSION_TIMEOUT_SECONDS = 20.0

#: The SDK caches the tool list per connection when asked. Enabled
#: because re-discovering tools on every agent run adds a round trip to
#: every invocation for data that changes on the order of days
#: (`mcp-expert`: cache discovery with a sensible TTL).
CACHE_TOOLS_LIST = True


class TransportNotPermittedError(Exception):
    """A stored installation asked for a transport it may not use.

    Almost always means a custom (user-registered) server asked for
    `stdio`, which would be arbitrary command execution on the worker
    fleet. Raised rather than silently downgraded: a user who configured
    stdio should learn it is refused, not get a connection they did not
    ask for.
    """


@dataclass(frozen=True, slots=True)
class ServerConnectionSpec:
    """Everything needed to construct one SDK server object.

    Assembled by the caller from the installation row plus credentials
    resolved at call time. Credentials arrive here as plaintext and are
    never stored on this object beyond constructing the SDK client — it
    is a frozen value passed straight into the factory, not held.
    """

    installed_server_id: str
    workspace_id: str
    display_name: str
    transport: str
    #: Catalog-supplied for stdio, never user input.
    command: str | None = None
    command_args: tuple[str, ...] = ()
    #: Environment for a stdio process — where an API-key credential goes
    #: for servers that read one (the usual convention).
    env: dict[str, str] = field(default_factory=dict)
    endpoint_url: str | None = None
    #: Headers for HTTP transports — where a bearer token goes.
    headers: dict[str, str] = field(default_factory=dict)
    #: From the catalog. A user-registered server is never catalog-backed
    #: and therefore never permitted stdio.
    is_catalog_entry: bool = False
    #: Empty means every discovered tool. Non-empty narrows, via the
    #: SDK's own filter.
    allowed_tools: tuple[str, ...] = ()


async def build_server(spec: ServerConnectionSpec) -> MCPServer:
    """Constructs the SDK server object for one installation.

    Async because HTTP transports validate their endpoint through the
    egress guard first. That pre-flight is *not* the main control — the
    guarded transport re-checks every hop — but failing here gives a
    clear, immediate error at connect time rather than a confusing
    transport failure later.
    """
    tool_filter = (
        create_static_tool_filter(allowed_tool_names=list(spec.allowed_tools))
        if spec.allowed_tools
        else None
    )

    if spec.transport == "stdio":
        return _build_stdio(spec, tool_filter)
    if spec.transport in ("sse", "streamable_http"):
        return await _build_http(spec, tool_filter)
    raise TransportNotPermittedError(f"unknown transport {spec.transport!r}")


def _build_stdio(spec: ServerConnectionSpec, tool_filter: Any) -> MCPServer:
    """stdio spawns a local process — the narrowest path in this module.

    Permitted only for catalog entries, whose command comes from the
    catalog row. A user-supplied command would be remote code execution
    on the worker fleet with extra steps (ADR-0010), so this refuses
    rather than trusting a caller to have checked.
    """
    if not spec.is_catalog_entry:
        raise TransportNotPermittedError(
            "stdio transport is only available for vetted catalog entries. "
            "A custom server must use an HTTP transport."
        )
    if not spec.command:
        raise TransportNotPermittedError("stdio transport requires a command from the catalog")

    params: MCPServerStdioParams = {"command": spec.command, "args": list(spec.command_args)}
    if spec.env:
        params["env"] = dict(spec.env)

    return MCPServerStdio(
        params=params,
        cache_tools_list=CACHE_TOOLS_LIST,
        name=spec.display_name,
        client_session_timeout_seconds=CLIENT_SESSION_TIMEOUT_SECONDS,
        tool_filter=tool_filter,
    )


async def _build_http(spec: ServerConnectionSpec, tool_filter: Any) -> MCPServer:
    if not spec.endpoint_url:
        raise TransportNotPermittedError(f"{spec.transport} transport requires an endpoint URL")

    # Pre-flight. The guarded transport is the real control, but failing
    # here turns "your server is unreachable" into "that address is not
    # permitted, and here is why".
    try:
        await validate_destination(spec.endpoint_url)
    except EgressDeniedError:
        logger.warning(
            "mcp_endpoint_denied workspace_id=%s server_id=%s",
            spec.workspace_id,
            spec.installed_server_id,
        )
        raise

    if spec.transport == "sse":
        sse_params: MCPServerSseParams = {
            "url": spec.endpoint_url,
            "headers": dict(spec.headers),
            "httpx_client_factory": guarded_http_client_factory,
        }
        return MCPServerSse(
            params=sse_params,
            cache_tools_list=CACHE_TOOLS_LIST,
            name=spec.display_name,
            client_session_timeout_seconds=CLIENT_SESSION_TIMEOUT_SECONDS,
            tool_filter=tool_filter,
        )

    http_params: MCPServerStreamableHttpParams = {
        "url": spec.endpoint_url,
        "headers": dict(spec.headers),
        "httpx_client_factory": guarded_http_client_factory,
    }
    return MCPServerStreamableHttp(
        params=http_params,
        cache_tools_list=CACHE_TOOLS_LIST,
        name=spec.display_name,
        client_session_timeout_seconds=CLIENT_SESSION_TIMEOUT_SECONDS,
        tool_filter=tool_filter,
    )


def credential_placement(
    auth_scheme: str, key: str, value: str
) -> tuple[dict[str, str], dict[str, str]]:
    """Decides where a resolved credential goes: env or header.

    Returns `(env, headers)`. One function rather than a branch at each
    call site, so "where does an API key go for this scheme" has exactly
    one answer and rotating a credential cannot accidentally place it
    differently from how it was placed at install time.

    Credentials are never logged here and never returned to a caller that
    might log them — they go straight into the SDK params.
    """
    env: dict[str, str] = {}
    headers: dict[str, str] = {}

    match auth_scheme:
        case "bearer_token" | "oauth2" | "jwt":
            headers["Authorization"] = f"Bearer {value}"
        case "basic":
            # The stored value is already the base64 `user:pass` blob —
            # assembling it here would mean storing two credentials and
            # joining them at call time, which is more moving parts for
            # the same result.
            headers["Authorization"] = f"Basic {value}"
        case "custom_header":
            # The credential's `key` *is* the header name for this
            # scheme; that is what makes it custom.
            headers[key] = value
        case "api_key":
            # stdio servers overwhelmingly read API keys from the
            # environment (the convention every published MCP server
            # follows); HTTP servers get it as a header under the same
            # name. Both are populated because the transport decides
            # which one is read, and the caller knows the transport.
            env[key] = value
            headers[key] = value
        case _:
            env[key] = value

    return env, headers
