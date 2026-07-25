"""`/internal/auth-events` — Better Auth (apps/web) reports signup/login
here so `audit_logs` stays the single home for every auth-relevant
event (ADR-0005). Not part of the public `/api/v1` surface.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.application.auth_event_service import AuthEventService
from agentverse_api.auth_service.infrastructure.repositories import SqlAuditLogRepository
from agentverse_api.auth_service.interface.dependencies.internal_service_auth import (
    require_internal_service,
)
from agentverse_api.auth_service.interface.schemas.auth_event import RecordAuthEventRequest
from agentverse_api.infrastructure.db import get_db_session

router = APIRouter(
    prefix="/internal/auth-events",
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
)


@router.post("", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def record_auth_event(
    body: RecordAuthEventRequest,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    service = AuthEventService(audit=AuditService(audit_logs=SqlAuditLogRepository(session)))
    await service.record_auth_event(event_type=body.event_type, user_id=body.user_id)
