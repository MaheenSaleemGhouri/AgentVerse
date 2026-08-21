"""Builds AgentVerse's own MCP server (docs/adr/0017) — a single global
`FastMCP` instance registered into the main FastAPI app as a raw
`Route("/mcp", ...)` (`main.py`, so this sub-app's own `/mcp` route is
reached with no redirect hop and without shadowing any other route in
the app), never a separate server process. Streamable HTTP is the
transport (the current MCP spec's recommended remote transport), not
stdio — this is a hosted, multi-tenant server, not a local subprocess.

Workspace is resolved from the credential (`auth.py`), never from the
URL — `/mcp` is not workspace-prefixed, matching how `api_keys` are
already workspace-scoped at issuance rather than at every call site.
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from agentverse_api.infrastructure.config import Settings, get_settings
from agentverse_api.orchestration_service.interface.mcp_server.auth import ApiKeyTokenVerifier
from agentverse_api.orchestration_service.interface.mcp_server.tools import register_tools


def _transport_security(settings: Settings) -> TransportSecuritySettings:
    """DNS-rebinding protection (`TransportSecurityMiddleware`), kept
    enabled — never disabled — with the real public host added to the
    SDK's own localhost-only default allowlist.

    `FastMCP` only auto-populates `allowed_hosts`/`allowed_origins` when
    its `host=` constructor arg is a loopback address (its own default,
    `"127.0.0.1"`) — which we never override, so without this, the
    resolved allowlist stays loopback-only forever and a genuinely
    deployed `/mcp` would 421 on every real client's Host header. Both a
    bare (no-port, matching a request made over the scheme's *default*
    port — 80/443 — where a Host header omits the port entirely) and a
    `:*` wildcard (matching a Host header with an explicit port) entry
    are added for every host, since the matcher does exact-or-wildcard
    matching only, never implicit port-optionality. The SDK's own
    hardcoded loopback defaults only ever added the wildcard form, which
    is why a plain `http://localhost` (default port 80, so `Host:
    localhost` with no port) previously 421'd even locally.
    """
    public = urlsplit(settings.api_public_url)
    host = public.netloc  # e.g. "api.agentverse.io" or "api.agentverse.io:8443"
    bare_host = public.hostname or host
    origin = f"{public.scheme}://{host}"
    bare_origin = f"{public.scheme}://{bare_host}"
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "127.0.0.1",
            "127.0.0.1:*",
            "localhost",
            "localhost:*",
            "[::1]",
            "[::1]:*",
            host,
            bare_host,
            f"{bare_host}:*",
        ],
        allowed_origins=[
            "http://127.0.0.1",
            "http://127.0.0.1:*",
            "http://localhost",
            "http://localhost:*",
            "http://[::1]",
            "http://[::1]:*",
            origin,
            bare_origin,
            f"{bare_origin}:*",
        ],
    )


def _build_mcp(settings: Settings) -> FastMCP:
    mcp = FastMCP(
        name="AgentVerse",
        instructions=(
            "Run and inspect AgentVerse agents and workflows in the workspace this "
            "MCP client credential was issued for."
        ),
        # Left at the SDK default (`/mcp`) deliberately: `main.py` registers
        # this sub-app as a raw `Route("/mcp", endpoint=mcp_asgi_app())`,
        # not a `Mount` at any prefix — a `Mount("/mcp", ...)` redirects a
        # bare hit on its own prefix to add a trailing slash (`POST /mcp`
        # 307s to `/mcp/`, breaking a real client that doesn't follow
        # redirects on a POST), so the sub-app must own this exact path
        # itself and be reached without any prefix-stripping in between.
        token_verifier=ApiKeyTokenVerifier(),
        auth=AuthSettings(
            # No real OAuth authorization server behind this — credentials
            # are pre-issued `av_live_...` bearer tokens (the MCP-clients
            # settings page), verified by `ApiKeyTokenVerifier` alone.
            # `issuer_url`/`resource_server_url` are required by
            # `AuthSettings` for the Protected Resource Metadata endpoint
            # it still publishes; both point at this same API origin
            # since there is no separate authorization server to name.
            issuer_url=settings.api_public_url,
            resource_server_url=f"{settings.api_public_url}/mcp",
        ),
        transport_security=_transport_security(settings),
        stateless_http=True,
    )
    register_tools(mcp)
    return mcp


@lru_cache
def get_mcp_server() -> FastMCP:
    return _build_mcp(get_settings())


def mcp_asgi_app() -> Starlette:
    """The Starlette ASGI app `main.py` registers as `Route("/mcp", ...)`
    (this sub-app declares its own `/mcp` route internally, matched
    directly since a `Route` endpoint receives the request's path
    unmodified) — auth middleware (`AuthenticationMiddleware` +
    `RequireAuthMiddleware`) is wired automatically by
    `streamable_http_app()` because `auth=` was passed to `FastMCP`
    above.
    """
    return get_mcp_server().streamable_http_app()
