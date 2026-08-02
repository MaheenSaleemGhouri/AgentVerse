"""Resource-scoped permission check — composed *alongside* a
`require_role`/`require_org_role` dependency on the same route, never in
place of one. `Depends(require_viewer), Depends(require_resource_permission("agent", "publish"))`
is the intended shape: the role floor still gates baseline access, this
adds an orthogonal grant on top. A route that only depends on
`require_role` today is unaffected by this file's existence — nothing
about `require_role`'s behavior or signature changes.

Mirrors `require_role.py`'s audit-on-denial contract exactly
(`resource_permission.denied`, committed explicitly so the denial write
survives the `HTTPException` that follows it).
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.infrastructure.repositories import (
    SqlAuditLogRepository,
    SqlResourcePermissionRepository,
)
from agentverse_api.auth_service.interface.dependencies.get_current_workspace import (
    get_current_workspace,
)
from agentverse_api.infrastructure.db import get_db_session

_USER_PRINCIPAL_TYPE = "user"


def require_resource_permission(
    resource_type: str, permission: str, *, resource_id: str = ""
) -> Callable[..., Coroutine[Any, Any, None]]:
    """Dependency factory: `Depends(require_resource_permission("billing", "manage"))`.

    `resource_id` defaults to `""` — "applies to every resource of
    `resource_type` in the workspace" — the right default for
    workspace-wide resource types (billing has no individual instances);
    pass a concrete id to scope the check to one specific resource.
    """

    async def _dependency(
        context: WorkspaceContext = Depends(get_current_workspace),
        session: AsyncSession = Depends(get_db_session),
    ) -> None:
        repo = SqlResourcePermissionRepository(session)
        granted = await repo.check(
            workspace_id=context.workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
            principal_type=_USER_PRINCIPAL_TYPE,
            principal_id=context.user_id,
            permission=permission,
        )
        if granted:
            return

        audit = AuditService(audit_logs=SqlAuditLogRepository(session))
        await audit.record(
            action="resource_permission.denied",
            outcome="denied",
            workspace_id=context.workspace_id,
            actor_user_id=context.user_id,
            metadata={
                "resource_type": resource_type,
                "resource_id": resource_id,
                "permission": permission,
            },
        )
        # Commit explicitly — see `require_role.py`'s identical comment:
        # the HTTPException below would otherwise roll back this write too.
        await session.commit()

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Missing resource permission"
        )

    return _dependency
