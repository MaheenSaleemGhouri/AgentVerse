"""`GET .../runs/{run_id}/stream` — live execution-trace streaming
(docs/roadmap.md Phase 4; `decision-log.md` #19: SSE reading Redis
pub/sub). See `docs/adr/0007-sse-run-streaming-contract.md` for the
full event-shape contract.

Backfills already-persisted `agent_run_steps` first — a client
reconnecting mid-run sees the run's history, not just whatever happens
to be published after it reconnects (`decision-log.md` #19's own
rationale for choosing SSE) — then subscribes to `run:{run_id}:events`
for anything new, closing the stream once a terminal step/status is
observed. The pub/sub subscription is always released in a `finally`
block, including on client disconnect (`fastapi-expert`: a streaming
endpoint that leaks its Redis subscription is a defect, not an edge
case).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import require_viewer
from agentverse_api.orchestration_service.domain.ports.run_repository import AgentRunRepository
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_agent_run_repository,
    get_redis_client,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/agents/{agent_id}/runs", tags=["runs"])

_TERMINAL_STEP_TYPES = {"run_completed", "run_failed"}
_TERMINAL_RUN_STATUSES = {"success", "error", "cancelled"}


def channel_name(run_id: str) -> str:
    return f"run:{run_id}:events"


def sse_frame(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def stream_run_events(
    run_repo: AgentRunRepository, redis: Redis, *, run_id: str, run_status: str
) -> AsyncIterator[str]:
    """The actual streaming logic, factored out of the route handler so
    it's directly unit-testable (call it with a fake repo/redis and
    iterate) without needing to fight `httpx`/ASGI timing to exercise
    concurrent pub/sub delivery (CLAUDE.md §11).
    """
    already_finished = False
    for step in await run_repo.list_steps(run_id=run_id):
        yield sse_frame(
            {
                "type": step.step_type,
                "sequence": step.sequence,
                "payload": step.payload,
                "cost_micro_usd": step.cost_micro_usd,
            }
        )
        if step.step_type in _TERMINAL_STEP_TYPES:
            already_finished = True

    if already_finished or run_status in _TERMINAL_RUN_STATUSES:
        # The run was already done before this client connected —
        # nothing will ever be published for it. Close immediately
        # rather than opening a pub/sub subscription that sits idle
        # forever.
        return

    pubsub = redis.pubsub()
    channel = channel_name(run_id)
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            data = json.loads(message["data"])
            yield sse_frame(data)
            if data.get("type") in _TERMINAL_STEP_TYPES:
                return
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()  # type: ignore[no-untyped-call]  # redis-py's own stub is untyped here


@router.get("/{run_id}/stream")
async def stream_run(
    agent_id: str,
    run_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    run_repo: AgentRunRepository = Depends(get_agent_run_repository),
    redis: Redis = Depends(get_redis_client),
) -> StreamingResponse:
    run = await run_repo.get_run(workspace_id=context.workspace_id, run_id=run_id)
    if run is None or run.agent_id != agent_id:
        # 404, never a leaked "wrong agent_id" detail — same tenant-
        # isolation discipline as every other workspace-scoped lookup.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    return StreamingResponse(
        stream_run_events(run_repo, redis, run_id=run_id, run_status=run.status),
        media_type="text/event-stream",
    )
