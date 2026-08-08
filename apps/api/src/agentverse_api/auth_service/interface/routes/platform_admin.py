"""`/api/v1/admin/session` — "is the caller platform staff?"

Exists so the dashboard can decide whether to render the moderation
entry point without probing a gated route and swallowing the 404. That
probe would also write a `platform_admin.denied` audit entry on every
page load for every ordinary user, burying the denials that matter in
noise — the audit trail is evidence, and evidence that fires constantly
stops being read.

Answering `false` leaks nothing: the caller already knows whether they
are staff, and the moderation routes themselves stay 404-on-denial.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.infrastructure.repositories import SqlPlatformAdminRepository
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
)
from agentverse_api.infrastructure.db import get_db_session

router = APIRouter(prefix="/api/v1/admin", tags=["platform-admin"])


class PlatformAdminSessionResponse(BaseModel):
    is_platform_admin: bool


@router.get("/session", response_model=PlatformAdminSessionResponse)
async def platform_admin_session_route(
    user_id: str = Depends(get_current_identity),
    session: AsyncSession = Depends(get_db_session),
) -> PlatformAdminSessionResponse:
    """Authenticated, deliberately not authorized past that.

    A non-staff caller gets `false`, not a 404 — this is the one route
    whose whole purpose is to answer the question, and gating it would
    make it useless for the thing it exists to do.
    """
    admins = SqlPlatformAdminRepository(session)
    return PlatformAdminSessionResponse(is_platform_admin=await admins.is_platform_admin(user_id))
