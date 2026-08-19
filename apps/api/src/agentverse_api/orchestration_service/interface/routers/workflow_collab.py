"""Workflow-canvas real-time collaboration (docs/adr/0016) — the
platform's first legitimate WebSocket use case (`decision-log.md` #20:
reserved for genuinely bidirectional, low-latency interaction).

Scope is deliberately presence + node-position/edge broadcast, not
operational-transform text co-editing — last-write-wins per node is the
documented conflict rule, since no acceptance criterion asks for more.

`POST .../collab-ticket` mints the short-lived auth ticket over normal
authenticated REST; `GET .../collab` (a WebSocket upgrade) validates and
burns it during the handshake, before `accept()`. The relay loop itself
lives in `application/workflow_collab_relay.py` — this route is just the
FastAPI/WebSocket binding around it.
"""

from __future__ import annotations

import contextlib
import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from redis.asyncio import Redis

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import require_viewer
from agentverse_api.infrastructure.config import Settings, get_settings
from agentverse_api.orchestration_service.application.workflow_collab_relay import run_relay_loop
from agentverse_api.orchestration_service.application.workflow_collab_ticket import (
    mint_ticket,
    resolve_and_burn_ticket,
)
from agentverse_api.orchestration_service.interface.dependencies.services import get_redis_client
from agentverse_api.orchestration_service.interface.schemas.workflow_collab import (
    CollabTicketResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/workflows/{workflow_id}", tags=["workflows"]
)


def _channel(workflow_id: str) -> str:
    return f"workflow:{workflow_id}:collab"


@router.post("/collab-ticket", response_model=CollabTicketResponse)
async def mint_collab_ticket_route(
    workflow_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    redis: Redis = Depends(get_redis_client),
) -> CollabTicketResponse:
    ticket, expires_in = await mint_ticket(
        workspace_id=context.workspace_id,
        workflow_id=workflow_id,
        user_id=context.user_id,
        role=context.role.value,
        redis=redis,
    )
    return CollabTicketResponse(ticket=ticket, expires_in_seconds=expires_in)


@router.websocket("/collab")
async def workflow_collab_ws(
    websocket: WebSocket,
    workspace_id: str,
    workflow_id: str,
    ticket: str = Query(...),
    settings: Settings = Depends(get_settings),
    redis: Redis = Depends(get_redis_client),
) -> None:
    origin = websocket.headers.get("origin")
    if origin is not None and origin != settings.auth_public_url:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    resolved = await resolve_and_burn_ticket(ticket=ticket, redis=redis)
    if (
        resolved is None
        or resolved.workspace_id != workspace_id
        or resolved.workflow_id != workflow_id
    ):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    with contextlib.suppress(WebSocketDisconnect):
        await run_relay_loop(
            websocket, redis=redis, channel=_channel(workflow_id), user_id=resolved.user_id
        )
