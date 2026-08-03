"""`/api/v1/workspaces/{workspace_id}/audit-logs` — read path for the
append-only `audit_logs` table (CLAUDE.md §7 REST conventions).

Admin-gated, not viewer/member: audit history is itself sensitive
(who did what, including permission denials) and its visibility floor
is deliberately higher than ordinary workspace reads.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from agentverse_api.auth_service.application.audit_export import to_csv, to_json
from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import require_admin
from agentverse_api.auth_service.interface.dependencies.services import get_audit_service
from agentverse_api.auth_service.interface.schemas.audit_log import (
    AuditActivityPoint,
    AuditActivityResponse,
    AuditLogPage,
    AuditLogResponse,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["audit-logs"])

#: Matches the runtime tool-call log's own ceiling
#: (`orchestration_service/interface/routers/integrations.py`) — the same
#: high-volume, append-only-log pagination shape.
MAX_PAGE_SIZE = 200

#: Hard ceiling on one export. An append-only table grows without bound,
#: so an unbounded export is a denial-of-service on this service's own
#: memory. A workspace needing more than this should page the JSON API.
MAX_EXPORT_ROWS = 10_000


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


@router.get("/{workspace_id}/audit-logs/activity", response_model=AuditActivityResponse)
async def audit_activity_route(
    days: int = Query(default=30, ge=1, le=365),
    context: WorkspaceContext = Depends(require_admin),
    service: AuditService = Depends(get_audit_service),
) -> AuditActivityResponse:
    """Daily entry counts for the activity graph, gap-filled to zero."""
    counts = await service.activity_by_day(workspace_id=context.workspace_id, days=days)
    return AuditActivityResponse(
        points=[AuditActivityPoint(day=day, count=count) for day, count in counts],
        total=sum(count for _, count in counts),
    )


@router.get("/{workspace_id}/audit-logs/export", response_class=Response)
async def export_audit_logs_route(
    export_format: Literal["csv", "json"] = Query(default="csv", alias="format"),
    action: str | None = Query(default=None, max_length=100),
    actor_user_id: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=MAX_EXPORT_ROWS, ge=1, le=MAX_EXPORT_ROWS),
    context: WorkspaceContext = Depends(require_admin),
    service: AuditService = Depends(get_audit_service),
) -> Response:
    """Exports the workspace's audit log as CSV or JSON.

    Bounded by `MAX_EXPORT_ROWS` rather than streaming the whole table:
    `audit_logs` is append-only and unbounded, so an unlimited export
    would be a denial-of-service against this service's own memory.

    The response is a download (`Content-Disposition: attachment`) with
    `X-Content-Type-Options: nosniff`, so a browser never renders
    attacker-influenced audit content as a document in this origin.
    """
    entries = await service.list_for_workspace(
        workspace_id=context.workspace_id,
        limit=limit,
        action=action,
        actor_user_id=actor_user_id,
    )
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    if export_format == "json":
        body, media_type, suffix = to_json(entries), "application/json", "json"
    else:
        # text/csv, not application/vnd.ms-excel: the file is CSV, and
        # claiming a spreadsheet type invites the client to open it in
        # one automatically.
        body, media_type, suffix = to_csv(entries), "text/csv", "csv"

    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="audit-logs-{context.workspace_id}-{stamp}.{suffix}"'
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )
