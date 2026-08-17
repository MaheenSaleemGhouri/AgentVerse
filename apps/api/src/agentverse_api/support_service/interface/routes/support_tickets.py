"""`/api/v1/workspaces/{workspace_id}/support-tickets` — Phase 11's
dogfooded support-triage surface.

Creating a ticket triggers a real agent run through the existing
`orchestration_service` run-submission path (`require_member`, matching
`agents.py`'s `submit_run_route`); reading one resolves the triage
result from that same run once it has finished (`require_viewer`).
`workspace_id` always comes from the authenticated context, never the
path (Rule 6).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_member,
    require_viewer,
)
from agentverse_api.orchestration_service.domain.run_exceptions import (
    AgentNotRunnableError,
    RunSubmissionConflictError,
)
from agentverse_api.support_service.application.support_ticket_service import (
    SupportTicketService,
)
from agentverse_api.support_service.interface.dependencies.services import (
    get_support_ticket_service,
)
from agentverse_api.support_service.interface.schemas.support_tickets import (
    CreateSupportTicketRequest,
    SupportTicketPage,
    SupportTicketResponse,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["support-tickets"])

MAX_PAGE_SIZE = 100


def _to_response(ticket: object) -> SupportTicketResponse:
    return SupportTicketResponse.model_validate(ticket, from_attributes=True)


@router.post(
    "/{workspace_id}/support-tickets",
    response_model=SupportTicketResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_support_ticket_route(
    body: CreateSupportTicketRequest,
    context: WorkspaceContext = Depends(require_member),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    service: SupportTicketService = Depends(get_support_ticket_service),
) -> SupportTicketResponse:
    """`202 Accepted`: this route itself triggers a real, asynchronously
    executed agent run (CLAUDE.md §7), the same run-triggering contract
    `submit_run_route` uses — including `Idempotency-Key` passthrough.
    """
    try:
        ticket = await service.create_ticket(
            workspace_id=context.workspace_id,
            agent_id=body.agent_id,
            subject=body.subject,
            body=body.body,
            created_by_user_id=context.user_id,
            idempotency_key=idempotency_key,
        )
    except AgentNotRunnableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Triage agent has no published version to run",
        ) from exc
    except RunSubmissionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not confirm triage submission — retry with the same Idempotency-Key",
        ) from exc
    return _to_response(ticket)


@router.get("/{workspace_id}/support-tickets", response_model=SupportTicketPage)
async def list_support_tickets_route(
    limit: int = Query(default=25, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
    context: WorkspaceContext = Depends(require_viewer),
    service: SupportTicketService = Depends(get_support_ticket_service),
) -> SupportTicketPage:
    rows = await service.list_tickets(
        workspace_id=context.workspace_id, limit=limit + 1, cursor=cursor
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return SupportTicketPage(
        data=[_to_response(ticket) for ticket in page],
        next_cursor=page[-1].created_at.isoformat() if has_more and page else None,
        has_more=has_more,
    )


@router.get(
    "/{workspace_id}/support-tickets/{ticket_id}", response_model=SupportTicketResponse
)
async def get_support_ticket_route(
    ticket_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    service: SupportTicketService = Depends(get_support_ticket_service),
) -> SupportTicketResponse:
    ticket = await service.get_ticket(workspace_id=context.workspace_id, ticket_id=ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such ticket")
    return _to_response(ticket)


@router.post(
    "/{workspace_id}/support-tickets/{ticket_id}/resolve",
    response_model=SupportTicketResponse,
)
async def resolve_support_ticket_route(
    ticket_id: str,
    context: WorkspaceContext = Depends(require_member),
    service: SupportTicketService = Depends(get_support_ticket_service),
) -> SupportTicketResponse:
    ticket = await service.resolve_ticket(workspace_id=context.workspace_id, ticket_id=ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such ticket")
    return _to_response(ticket)
