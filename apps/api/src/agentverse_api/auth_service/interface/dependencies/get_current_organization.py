"""Resolves `organization_id` from the authenticated identity's actual
membership — structurally identical to `get_current_workspace.py`
(ADR-0006). Organization access is fully independent of workspace
access: this dependency never consults `workspace_members`.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.domain.entities import OrganizationContext
from agentverse_api.auth_service.infrastructure.repositories import SqlOrganizationRepository
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
)
from agentverse_api.infrastructure.db import get_db_session


async def get_current_organization(
    organization_id: str = Path(...),
    user_id: str = Depends(get_current_identity),
    session: AsyncSession = Depends(get_db_session),
) -> OrganizationContext:
    repo = SqlOrganizationRepository(session)
    membership = await repo.get_membership(organization_id=organization_id, user_id=user_id)

    if membership is None:
        # 404, never 403: a non-member must not learn whether the
        # organization exists at all (CLAUDE.md Rule 11 / ADR-0004).
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
        )

    if membership.suspended_at is not None:
        # 403, not 404: the caller *is* a known member — existence isn't
        # in question, they are just currently blocked from acting.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Organization membership suspended"
        )

    return OrganizationContext(
        organization_id=organization_id, user_id=user_id, role=membership.role
    )
