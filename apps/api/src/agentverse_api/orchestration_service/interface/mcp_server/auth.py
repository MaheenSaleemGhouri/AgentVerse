"""Bearer-token verification for AgentVerse's own MCP server surface
(docs/adr/0017). The inverse trust direction from every other credential
in this codebase: the caller here is an external, untrusted MCP client
reaching *into* AgentVerse, not AgentVerse reaching out.

Implements the MCP SDK's own `TokenVerifier` protocol rather than a
hand-rolled auth layer — `mcp.server.auth.middleware.bearer_auth.
BearerAuthBackend` calls this, then Starlette's own
`AuthenticationMiddleware` stashes the result on `scope["user"]`, which
each tool call reads back via `ctx.request_context.request.user`
(`context.py`). Deliberately reuses the *exact same* `api_keys` lookup/
scope/role-ceiling logic `get_current_workspace._context_from_api_key`
already uses for the ordinary REST API — one permission model, not two —
scoped to `kind='mcp_client'` credentials only (`ApiKeyKind`).
"""

from __future__ import annotations

import time

from mcp.server.auth.provider import AccessToken, TokenVerifier

from agentverse_api.auth_service.application.api_key_service import ApiKeyService
from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.api_key_kind import ApiKeyKind
from agentverse_api.auth_service.domain.api_key_scope import effective_role
from agentverse_api.auth_service.infrastructure.repositories import (
    SqlApiKeyRepository,
    SqlAuditLogRepository,
    SqlWorkspaceRepository,
)
from agentverse_api.infrastructure.db import get_session_factory


class ApiKeyTokenVerifier(TokenVerifier):
    """Resolves a presented `av_live_...` credential to an `AccessToken`
    whose `claims` carry everything a tool call needs (`workspace_id`,
    `role`, `api_key_id`) — verified once per request here rather than
    re-queried per tool call.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        session_factory = get_session_factory()
        async with session_factory() as session:
            audit = AuditService(audit_logs=SqlAuditLogRepository(session))
            service = ApiKeyService(api_keys=SqlApiKeyRepository(session), audit=audit)

            key = await service.authenticate(token)
            if key is None or key.kind is not ApiKeyKind.MCP_CLIENT:
                # Same non-distinguishing failure as every other
                # rejection on this path (CLAUDE.md §10) — a
                # `user_api_key` presented here is rejected identically
                # to an unknown or revoked credential.
                return None

            workspaces = SqlWorkspaceRepository(session)
            membership = await workspaces.get_membership(
                workspace_id=key.workspace_id, user_id=key.created_by_user_id
            )
            if membership is None:
                await audit.record(
                    action="mcp_client.orphaned",
                    outcome="denied",
                    workspace_id=key.workspace_id,
                    actor_user_id=key.created_by_user_id,
                    target=key.id,
                    metadata={"reason": "issuer is no longer a member"},
                )
                await session.commit()
                return None

            role = effective_role(key.scope, membership.role)
            await session.commit()

            return AccessToken(
                token=token,
                client_id=key.id,
                scopes=[role.value],
                expires_at=int(key.expires_at.timestamp()) if key.expires_at else None,
                subject=key.created_by_user_id,
                claims={
                    "workspace_id": key.workspace_id,
                    "role": role.value,
                    "api_key_id": key.id,
                    "user_id": key.created_by_user_id,
                    "verified_at": int(time.time()),
                },
            )
