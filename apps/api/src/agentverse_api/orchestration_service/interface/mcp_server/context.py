"""Extracts the resolved MCP-client identity from a tool call's
`Context` — the bridge between `auth.py`'s `ApiKeyTokenVerifier` (which
runs once, outside any tool, during the Streamable HTTP handshake) and
each tool implementation (which needs `workspace_id`/`role` on every
call).

`ctx.request_context.request` is the raw Starlette `Request` the
`streamable_http_app()` handled — the same object Starlette's
`AuthenticationMiddleware` stashed `scope["user"]` on, so `.user` here
is the `AuthenticatedUser` `BearerAuthBackend` constructed from
`ApiKeyTokenVerifier`'s `AccessToken`, and `.claims` is exactly the
dict `auth.py` built.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.fastmcp import Context

from agentverse_api.auth_service.domain.role import Role, satisfies


class McpAuthenticationError(Exception):
    """Raised when a tool call arrives with no resolved MCP-client
    identity — should be unreachable in practice, since `RequireAuthMiddleware`
    already rejects an unauthenticated request before it reaches a tool,
    but a tool must never silently proceed with no workspace to scope to.
    """


class McpAuthorizationError(Exception):
    """Raised when the resolved credential's role does not satisfy a
    tool's minimum — surfaces to the MCP client as a plain tool error
    (`isError: true`), and is audited as `mcp_server.tool_denied`
    (`tools.py`) before it is raised.
    """


@dataclass(frozen=True, slots=True)
class ResolvedMcpContext:
    workspace_id: str
    user_id: str
    role: Role
    api_key_id: str


def resolve_context(ctx: Context[Any, Any, Any]) -> ResolvedMcpContext:
    request = ctx.request_context.request
    user = getattr(request, "user", None) if request is not None else None
    if not isinstance(user, AuthenticatedUser):
        raise McpAuthenticationError("No authenticated MCP client on this request")

    claims = user.access_token.claims or {}
    return ResolvedMcpContext(
        workspace_id=claims["workspace_id"],
        user_id=claims["user_id"],
        role=Role(claims["role"]),
        api_key_id=claims["api_key_id"],
    )


def require_role(resolved: ResolvedMcpContext, minimum: Role) -> None:
    if not satisfies(resolved.role, minimum):
        raise McpAuthorizationError(
            f"This MCP client's role ({resolved.role.value}) does not permit this tool "
            f"(needs at least {minimum.value})"
        )
