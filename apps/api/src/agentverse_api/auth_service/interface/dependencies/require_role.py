"""Deny-by-default role check, composed on top of `get_current_workspace`
(ADR-0004). A denial is written to `audit_logs` from this single
enforcement point, never left to the calling route to remember.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.domain.role import Role, satisfies
from agentverse_api.auth_service.infrastructure.repositories import SqlAuditLogRepository
from agentverse_api.auth_service.interface.dependencies.get_current_workspace import (
    get_current_workspace,
)
from agentverse_api.infrastructure.db import get_db_session


def require_role(
    minimum: Role,
) -> Callable[..., Coroutine[Any, Any, WorkspaceContext]]:
    """Dependency factory: `Depends(require_role(Role.ADMIN))`."""

    async def _dependency(
        context: WorkspaceContext = Depends(get_current_workspace),
        session: AsyncSession = Depends(get_db_session),
    ) -> WorkspaceContext:
        if satisfies(context.role, minimum):
            return context

        audit = AuditService(audit_logs=SqlAuditLogRepository(session))
        await audit.record(
            action="permission.denied",
            outcome="denied",
            workspace_id=context.workspace_id,
            actor_user_id=context.user_id,
            metadata={"required_role": minimum.value, "actual_role": context.role.value},
        )
        # Commit explicitly: the HTTPException raised below propagates
        # through get_db_session's yield, which rolls back on exception.
        # Without this, the denial we just wrote would be rolled back
        # along with it — the one event this dependency exists to record
        # would silently vanish.
        await session.commit()

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")

    return _dependency


# Pre-built for the three role floors every current route needs — routes
# depend on these singletons (`Depends(require_viewer)`) rather than
# calling `require_role(Role.X)` inline, so the factory call happens
# once at import time, not on every request.
require_viewer = require_role(Role.VIEWER)
require_admin = require_role(Role.ADMIN)
require_owner = require_role(Role.OWNER)
