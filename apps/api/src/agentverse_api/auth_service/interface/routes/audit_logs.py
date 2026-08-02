"""`/api/v1/workspaces/{workspace_id}/audit-logs` — read path for the
append-only `audit_logs` table (CLAUDE.md §7 REST conventions).

Admin-gated, not viewer/member: audit history is itself sensitive
(who did what, including permission denials) and its visibility floor
is deliberately higher than ordinary workspace reads.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import require_admin
from agentverse_api.auth_service.interface.dependencies.services import get_audit_service
from agentverse_api.auth_service.interface.schemas.audit_log import AuditLogPage, AuditLogResponse

router = APIRouter(prefix="/api/v1/workspaces", tags=["audit-logs"])

#: Matches the runtime tool-call log's own ceiling
#: (`orchestration_service/interface/routers/integrations.py`) — the same
#: high-volume, append-only-log pagination shape.
MAX_PAGE_SIZE = 200


@router.get("/{workspace_id}/audit-logs", response_model=AuditLogPage)
async def list_audit_logs_route(
    action: str | None = Query(default=None, max_length=100),
    actor_user_id: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
    context: WorkspaceContext = Depends(require_admin),
    service: AuditService = Depends(get_audit_service),
) -> AuditLogPage:
    """Cursor-paginated on `created_at`, matching the runtime-log
    convention (CLAUDE.md §7) — offset pagination on a fast-appending
    table skips and repeats rows as new entries land mid-page.
    """
    rows = await service.list_for_workspace(
        workspace_id=context.workspace_id,
        limit=limit + 1,
        cursor=cursor,
        action=action,
        actor_user_id=actor_user_id,
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return AuditLogPage(
        data=[
            AuditLogResponse(
                id=entry.id,
                workspace_id=entry.workspace_id,
                actor_user_id=entry.actor_user_id,
                action=entry.action,
                target=entry.target,
                outcome=entry.outcome,
                metadata=entry.metadata,
                created_at=entry.created_at,
            )
            for entry in page
        ],
        next_cursor=page[-1].created_at.isoformat() if has_more and page else None,
        has_more=has_more,
    )
