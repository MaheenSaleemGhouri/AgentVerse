"""Egress-guarded HTTP transport for MCP connections.

The SDK's HTTP transports accept an `httpx_client_factory`, and MCP's
default factory sets `follow_redirects=True`. That matters: a guard that
validates only the URL it was handed never sees the redirect hops, so a
server answering `302 → http://169.254.169.254/…` walks straight past it.

httpx invokes the transport once **per hop**, including redirects. So the
check belongs in the transport, not in a pre-flight call. Every request
httpx makes on this client — initial, redirected, or retried — is
validated before a socket opens.

This is the in-process layer of a two-layer control. Worker egress
network policy at the infrastructure layer is the other; neither is
trusted alone (CLAUDE.md §10, threat model T1).
"""

from __future__ import annotations

import httpx
from agentverse_shared.security.egress_guard import EgressDeniedError, validate_destination


class GuardedAsyncTransport(httpx.AsyncHTTPTransport):
    """Validates every outbound request through the egress guard.

    Subclasses the real transport rather than wrapping a client, because
    the transport is the last thing httpx calls before it dials — there
    is no layer below this one where a redirect could slip past.
    """

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        try:
            await validate_destination(str(request.url))
        except EgressDeniedError as exc:
            # Re-raised as a ConnectError so httpx's own machinery treats
            # it as a transport failure. The reason is preserved in the
            # message and surfaces in `tool_calls.denial_reason` — a
            # blocked attempt that lost its reason would be unauditable.
            raise httpx.ConnectError(f"egress denied: {exc.reason}", request=request) from exc
        return await super().handle_async_request(request)


def guarded_http_client_factory(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """Matches MCP's `McpHttpClientFactory` protocol.

    Deliberately keeps `follow_redirects=True` to match MCP's default —
    legitimate servers do redirect, and disabling it would break them.
    Safety comes from the transport validating each hop rather than from
    refusing to follow any.

    The redirect ceiling is lower than httpx's default of 20: a chain
    that long is either a misconfiguration or an attempt to exhaust the
    validator, and no real MCP server needs it.
    """
    return httpx.AsyncClient(
        headers=headers,
        timeout=timeout if timeout is not None else httpx.Timeout(30.0),
        auth=auth,
        follow_redirects=True,
        max_redirects=5,
        transport=GuardedAsyncTransport(),
    )
