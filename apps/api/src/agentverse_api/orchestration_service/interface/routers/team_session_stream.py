"""`GET .../teams/{team_id}/sessions/{session_id}/stream` — live
multi-agent runtime streaming.

Same contract as the single-agent SSE route (`docs/adr/0007`): backfill
the durable `execution_events` first so a client reconnecting mid-session
sees the whole run rather than only what happens after it reconnects,
then subscribe to `team_session:{session_id}:events` for anything new,
and always release the subscription in a `finally` — including on client
disconnect.

The event vocabulary is wider than the single-agent one (`agent_started`,
`handoff`, `agent_failed`, …), and it is deliberately open: the set grows
per topology, and a new event type must never require a migration to
start being recorded. The frontend's exhaustive union is the enforcement
point, so an unhandled type fails the build rather than being silently
dropped at runtime.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import require_viewer
from agentverse_api.orchestration_service.domain.ports.team_repository import TeamRepository
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_redis_client,
    get_team_repository,
)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/teams/{team_id}/sessions", tags=["teams"]
)

_TERMINAL_EVENT_TYPES = {"session_completed", "session_failed"}
_TERMINAL_SESSION_STATUSES = {"success", "error", "cancelled"}

#: Backfill cap. A session that produced more events than this is
#: readable in full through the paged `/events` endpoint — the stream's
#: job is to catch a client up quickly, not to be a bulk export.
_BACKFILL_LIMIT = 500


def channel_name(session_id: str) -> str:
    return f"team_session:{session_id}:events"


def sse_frame(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


async def stream_team_events(
    repo: TeamRepository,
    redis: Redis,
    *,
    workspace_id: str,
    session_id: str,
    session_status: str,
) -> AsyncIterator[str]:
    """Factored out of the route handler so it is directly unit-testable
    with a fake repo and Redis, without fighting ASGI timing to exercise
    concurrent pub/sub delivery (CLAUDE.md §11).
    """
    already_finished = False
    events = await repo.list_events(
        workspace_id=workspace_id, session_id=session_id, after_sequence=0, limit=_BACKFILL_LIMIT
    )
    for event in events:
        yield sse_frame(
            {
                "type": event["type"],
                "sequence": event["sequence"],
                "agent_id": event["agent_id"],
                "payload": event["payload"],
                "cost_micro_usd": event["cost_micro_usd"],
            }
        )
        if event["type"] in _TERMINAL_EVENT_TYPES:
            already_finished = True

    if already_finished or session_status in _TERMINAL_SESSION_STATUSES:
        # Nothing will ever be published for a finished session. Close
        # rather than opening a subscription that sits idle forever.
        return

    pubsub = redis.pubsub()
    channel = channel_name(session_id)
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = json.loads(message["data"])
            yield sse_frame(data)
            if data.get("type") in _TERMINAL_EVENT_TYPES:
                return
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()  # type: ignore[no-untyped-call]  # redis-py's own stub is untyped here


@router.get("/{session_id}/stream")
async def stream_team_session(
    team_id: str,
    session_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    repo: TeamRepository = Depends(get_team_repository),
    redis: Redis = Depends(get_redis_client),
) -> StreamingResponse:
    session = await repo.get_session(workspace_id=context.workspace_id, session_id=session_id)
    if session is None or session.team_id != team_id:
        # 404, never a leaked "wrong team_id" — same tenant-isolation
        # discipline as every other workspace-scoped lookup.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team session not found")

    return StreamingResponse(
        stream_team_events(
            repo,
            redis,
            workspace_id=context.workspace_id,
            session_id=session_id,
            session_status=session.status.value,
        ),
        media_type="text/event-stream",
    )
