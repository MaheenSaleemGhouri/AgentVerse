"""Deny-by-default check for platform-staff authority.

Composed on `get_current_identity`, **not** on `get_current_workspace` —
that is the whole point. Every other permission in this platform answers
"what may this identity do inside this workspace", but moderating the
marketplace is a judgement about a listing owned by a *different*
workspace, and no workspace role can express it. Routing moderation
through `require_role` would have let a publisher approve themselves.

Denials are written to `audit_logs` from this single enforcement point,
mirroring `require_role`'s contract — including the explicit commit,
because the `HTTPException` below propagates through `get_db_session`'s
yield, which rolls back on exception. Without it the one event this
dependency exists to record would vanish with the request.

Grants are audit-logged too, not just denials. For an ordinary route
"someone with permission used it" is noise; for an action that publishes
a listing to every customer it is the record an incident review reads.
That happens at the moderation routes, which know *what* was approved —
this dependency only knows that the door opened.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.infrastructure.repositories import (
    SqlAuditLogRepository,
    SqlPlatformAdminRepository,
)
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
)
from agentverse_api.infrastructure.db import get_db_session


async def require_platform_admin(
    user_id: str = Depends(get_current_identity),
    session: AsyncSession = Depends(get_db_session),
) -> str:
    """Returns the acting user's id, so routes can attribute the action.

    404 rather than 403: the moderation surface should not confirm its
    own existence to a caller who has no business there, the same
    reasoning `get_current_workspace` already applies to workspaces.
    """
    admins = SqlPlatformAdminRepository(session)
    if await admins.is_platform_admin(user_id):
        return user_id

    audit = AuditService(audit_logs=SqlAuditLogRepository(session))
    await audit.record(
        action="platform_admin.denied",
        outcome="denied",
        # Platform authority is global, so there is no workspace to
        # attribute this to — the denial is a fact about the identity.
        workspace_id=None,
        actor_user_id=user_id,
    )
    await session.commit()

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
