"""Deny-by-default permission check, composed on `get_current_workspace`.

Structurally identical to `require_role` (ADR-0004) and deliberately so:
same single enforcement point, same audit-on-denial contract, same
commit-before-raise handling. What differs is the question asked —
`require_role` asks "is this caller at least tier X", this asks "may this
caller do Y to resource Z".

**This composes with `require_role`, it never replaces it.** Every route
gated only on a role floor today is byte-for-byte unaffected. A route
that wants both states both:

    Depends(require_viewer), Depends(require_permission(Permission.AGENT_RUN))

**Custom roles resolve here.** When the member holds a custom role, the
effective grant set is the base tier's inherited permissions unioned with
the role's additive grants. Resolution reads the database, so it lives in
this dependency rather than in `permission.py`, which stays pure and
unit-testable without I/O.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.domain.permission import Permission, has_permission
from agentverse_api.auth_service.infrastructure.repositories import (
    SqlAuditLogRepository,
    SqlCustomRoleRepository,
)
from agentverse_api.auth_service.interface.dependencies.get_current_workspace import (
    get_current_workspace,
)
from agentverse_api.infrastructure.db import get_db_session


async def resolve_permissions(
    session: AsyncSession, context: WorkspaceContext
) -> frozenset[Permission]:
    """Every permission the caller effectively holds in this workspace.

    The base tier's inherited set, plus any additive grants from a custom
    role. A custom role can only add — see `permission.py` for why
    subtraction would break the `require_role` floor.
    """
    from agentverse_api.auth_service.domain.permission import permissions_for

    base = permissions_for(context.role)
    if context.custom_role_id is None:
        return base

    repo = SqlCustomRoleRepository(session)
    granted = await repo.list_permissions(
        workspace_id=context.workspace_id, role_id=context.custom_role_id
    )
    return base | granted


def require_permission(
    permission: Permission,
) -> Callable[..., Coroutine[Any, Any, WorkspaceContext]]:
    """Dependency factory: `Depends(require_permission(Permission.AGENT_RUN))`."""

    async def _dependency(
        context: WorkspaceContext = Depends(get_current_workspace),
        session: AsyncSession = Depends(get_db_session),
    ) -> WorkspaceContext:
        # Fast path: no custom role means the pure matrix is the whole
        # answer, so the common case never touches the database.
        if context.custom_role_id is None:
            allowed = has_permission(context.role, permission)
        else:
            allowed = permission in await resolve_permissions(session, context)

        if allowed:
            return context

        audit = AuditService(audit_logs=SqlAuditLogRepository(session))
        await audit.record(
            action="permission.denied",
            outcome="denied",
            workspace_id=context.workspace_id,
            actor_user_id=context.user_id,
            metadata={
                "required_permission": permission.value,
                "actual_role": context.role.value,
                "custom_role_id": context.custom_role_id or "",
            },
        )
        # Same reason as `require_role`: the HTTPException propagates
        # through get_db_session's yield, which rolls back on exception,
        # and would take this denial record with it.
        await session.commit()

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing permission: {permission.value}",
        )

    return _dependency
