"""Resolves `workspace_id` from the authenticated identity's actual
membership — never trusted directly from the path parameter (ADR-0004).
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.infrastructure.repositories import SqlWorkspaceRepository
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
)
from agentverse_api.infrastructure.db import get_db_session


async def get_current_workspace(
    workspace_id: str = Path(...),
    user_id: str = Depends(get_current_identity),
    session: AsyncSession = Depends(get_db_session),
) -> WorkspaceContext:
    repo = SqlWorkspaceRepository(session)
    membership = await repo.get_membership(workspace_id=workspace_id, user_id=user_id)

    if membership is None:
        # 404, never 403: a non-member must not learn whether the
        # workspace exists at all (CLAUDE.md Rule 11 / ADR-0004).
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    return WorkspaceContext(workspace_id=workspace_id, user_id=user_id, role=membership.role)
