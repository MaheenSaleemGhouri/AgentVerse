"""`/api/v1/workspaces/{workspace_id}/notifications`.

`require_viewer` on all of them, including the writes. Marking a
notification read is not a privileged action — it is the reader saying
"I have seen this", and gating it to admins would leave a member unable
to clear a banner they are looking at. Read state is per workspace, so
one person clearing it clears it for everyone, which is the intent: the
workspace was told, and someone dealt with it.

Nothing here exposes an amount charged or a payment method — those live
on the admin-gated billing surface. A notification carries the fact and
a link; following the link is where authorization applies.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import require_viewer
from agentverse_api.notification_service.application.notification_service import (
    NotificationService,
)
from agentverse_api.notification_service.interface.dependencies.services import (
    get_notification_service,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["notifications"])


class NotificationResponse(BaseModel):
    id: str
    kind: str
    severity: str
    title: str
    body: str
    #: Relative to this app. A client that treats it as an absolute URL
    #: is wrong, which is why the field is named for a path.
    action_path: str | None
    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    data: list[NotificationResponse]
    #: Sent alongside the list so the bell's badge does not need a second
    #: request, and so it stays correct when the list is truncated by
    #: `limit`.
    unread_count: int


class MarkAllReadResponse(BaseModel):
    marked: int


@router.get("/{workspace_id}/notifications", response_model=NotificationListResponse)
async def list_notifications_route(
    context: WorkspaceContext = Depends(require_viewer),
    service: NotificationService = Depends(get_notification_service),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
) -> NotificationListResponse:
    notifications = await service.list_for(
        workspace_id=context.workspace_id, limit=limit, unread_only=unread_only
    )
    return NotificationListResponse(
        data=[
            NotificationResponse(
                id=notification.id,
                kind=notification.kind.value,
                severity=notification.severity.value,
                title=notification.title,
                body=notification.body,
                action_path=notification.action_path,
                is_read=notification.is_read,
                created_at=notification.created_at,
            )
            for notification in notifications
        ],
        unread_count=await service.unread_count(context.workspace_id),
    )


@router.post(
    "/{workspace_id}/notifications/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    # FastAPI asserts a 204 declares no body, and a handler annotated
    # `-> None` still gets an inferred `null` response model without
    # this. Same shape the auth service's 204 routes already use.
    response_model=None,
)
async def mark_read_route(
    notification_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    service: NotificationService = Depends(get_notification_service),
) -> None:
    """404 covers both "no such notification" and "not in this
    workspace".

    Deliberately the same answer: distinguishing them would let a caller
    probe another tenant's notification ids by watching which ones return
    403 (Rule 11 — cross-workspace access is denied without leaking
    existence).
    """
    marked = await service.mark_read(
        workspace_id=context.workspace_id, notification_id=notification_id
    )
    if not marked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No unread notification with that id in this workspace.",
        )


@router.post("/{workspace_id}/notifications/read-all", response_model=MarkAllReadResponse)
async def mark_all_read_route(
    context: WorkspaceContext = Depends(require_viewer),
    service: NotificationService = Depends(get_notification_service),
) -> MarkAllReadResponse:
    return MarkAllReadResponse(marked=await service.mark_all_read(context.workspace_id))
