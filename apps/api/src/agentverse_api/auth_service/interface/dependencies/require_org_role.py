"""Deny-by-default role check for organizations — structurally identical
to `require_role.py`, composed on top of `get_current_organization`
(ADR-0006). A denial is written to `audit_logs` from this single
enforcement point, mirroring `require_role`'s own contract.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.entities import OrganizationContext
from agentverse_api.auth_service.domain.role import Role, satisfies
from agentverse_api.auth_service.infrastructure.repositories import SqlAuditLogRepository
from agentverse_api.auth_service.interface.dependencies.get_current_organization import (
    get_current_organization,
)
from agentverse_api.infrastructure.db import get_db_session


def require_org_role(
    minimum: Role,
) -> Callable[..., Coroutine[Any, Any, OrganizationContext]]:
    """Dependency factory: `Depends(require_org_role(Role.ADMIN))`."""

    async def _dependency(
        context: OrganizationContext = Depends(get_current_organization),
        session: AsyncSession = Depends(get_db_session),
    ) -> OrganizationContext:
        if satisfies(context.role, minimum):
            return context

        audit = AuditService(audit_logs=SqlAuditLogRepository(session))
        await audit.record(
            action="org_permission.denied",
            outcome="denied",
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            metadata={"required_role": minimum.value, "actual_role": context.role.value},
        )
        # Commit explicitly — see `require_role.py`'s identical comment:
        # the HTTPException below would otherwise roll back this write too.
        await session.commit()

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")

    return _dependency


require_org_viewer = require_org_role(Role.VIEWER)
require_org_admin = require_org_role(Role.ADMIN)
require_org_owner = require_org_role(Role.OWNER)
