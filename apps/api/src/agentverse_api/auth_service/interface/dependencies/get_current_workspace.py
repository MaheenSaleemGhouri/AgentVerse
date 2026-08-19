"""Resolves `workspace_id` from the presented credential's actual
membership — never trusted directly from the path parameter (ADR-0004).

Two credentials reach this dependency:

- a **user session JWT**, resolved to a `workspace_members` row; and
- an **API key**, which is workspace-scoped at issuance. The key's own
  workspace must match the path, and the resulting role is the
  intersection of the key's scope and its issuer's *current* membership
  role (`domain/api_key_scope.effective_role`).

Both produce the same `WorkspaceContext`, so `require_role` and every
route composed on it are unchanged by API-key support — there is one
permission model, not two.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.application.api_key_service import ApiKeyService
from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.api_key_kind import ApiKeyKind
from agentverse_api.auth_service.domain.api_key_scope import effective_role
from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.infrastructure.repositories import (
    SqlApiKeyRepository,
    SqlAuditLogRepository,
    SqlWorkspaceRepository,
)
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    bearer_scheme,
    get_current_identity_optional,
)
from agentverse_api.infrastructure.db import get_db_session

#: 404, never 403: a caller without membership must not learn whether the
#: workspace exists at all (CLAUDE.md Rule 11 / ADR-0004). Raised
#: identically for "no such workspace", "not a member", and "API key
#: belongs to a different workspace".
_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")


async def get_current_workspace(
    workspace_id: str = Path(...),
    user_id: str | None = Depends(get_current_identity_optional),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> WorkspaceContext:
    if user_id is None:
        # `get_current_identity_optional` returns `None` only after
        # seeing an API key, and 401s outright when no credential was
        # presented — so `credentials` is populated here. Checked rather
        # than asserted: `assert` is stripped under `python -O`, and this
        # is an authentication path.
        if credentials is None:  # pragma: no cover - unreachable in practice
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token"
            )
        return await _context_from_api_key(
            token=credentials.credentials, workspace_id=workspace_id, session=session
        )

    repo = SqlWorkspaceRepository(session)
    membership = await repo.get_membership(workspace_id=workspace_id, user_id=user_id)
    if membership is None:
        raise _NOT_FOUND

    return WorkspaceContext(
        workspace_id=workspace_id,
        user_id=user_id,
        role=membership.role,
        custom_role_id=membership.custom_role_id,
    )


async def _context_from_api_key(
    *, token: str, workspace_id: str, session: AsyncSession
) -> WorkspaceContext:
    audit = AuditService(audit_logs=SqlAuditLogRepository(session))
    service = ApiKeyService(api_keys=SqlApiKeyRepository(session), audit=audit)

    key = await service.authenticate(token)
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key"
        )

    if key.kind is not ApiKeyKind.USER_API_KEY:
        # An MCP-client credential is scoped to `/mcp` only (Phase 12,
        # ADR-0017) — indistinguishable from an unknown key here, same
        # as every other rejection on this path (CLAUDE.md §10).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key"
        )

    if key.workspace_id != workspace_id:
        # A valid key aimed at someone else's workspace is answered
        # exactly like a nonexistent workspace — the key holder learns
        # nothing about what other tenants exist (Rule 11).
        raise _NOT_FOUND

    # The issuer's role is re-read on every request rather than frozen
    # into the key: demoting or removing a member must narrow the keys
    # they issued immediately, without an explicit revocation sweep.
    repo = SqlWorkspaceRepository(session)
    membership = await repo.get_membership(
        workspace_id=workspace_id, user_id=key.created_by_user_id
    )
    if membership is None:
        await audit.record(
            action="api_key.orphaned",
            outcome="denied",
            workspace_id=workspace_id,
            actor_user_id=key.created_by_user_id,
            target=key.id,
            metadata={"reason": "issuer is no longer a member"},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key"
        )

    return WorkspaceContext(
        workspace_id=workspace_id,
        user_id=key.created_by_user_id,
        role=effective_role(key.scope, membership.role),
        api_key_id=key.id,
        # The issuer's custom role travels with the key, so a key never
        # holds a grant its issuer lost — the same re-read-per-request
        # rule the base role already follows.
        custom_role_id=membership.custom_role_id,
    )
