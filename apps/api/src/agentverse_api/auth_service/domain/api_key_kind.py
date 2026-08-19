"""What an `api_keys` row is *for* — orthogonal to `ApiKeyScope` (how
much access it carries). A credential's kind is enforced at the
authentication boundary (`get_current_workspace` for `USER_API_KEY`,
the MCP server's token verifier for `MCP_CLIENT`), so a leaked MCP
integration token can never be replayed against the ordinary REST API
and vice versa — each credential is scoped to the one surface it was
issued for, not just to a role ceiling within that surface.
"""

from __future__ import annotations

from enum import StrEnum


class ApiKeyKind(StrEnum):
    #: A personal/service credential for the ordinary `/api/v1/*` REST API.
    USER_API_KEY = "user_api_key"
    #: A credential for AgentVerse's own MCP server surface (`/mcp`,
    #: docs/adr/0017) — never valid against `/api/v1/*`.
    MCP_CLIENT = "mcp_client"
