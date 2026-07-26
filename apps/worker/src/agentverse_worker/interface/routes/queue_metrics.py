"""Internal-only queue observability surface (docs/roadmap.md Phase 3:
"Add queue depth/DLQ-size metrics to the observability foundation
established in Phase 0"). Never reachable from a browser — this
service isn't internet-routable at all (CLAUDE.md §5) — so no
additional auth is layered on beyond that network boundary at this
lightweight-security stage of the phase.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agentverse_worker.interface.dependencies import get_queue
from agentverse_worker.queue.redis_stream_queue import RedisStreamQueue

router = APIRouter(prefix="/internal/queue", tags=["internal"])


class QueueMetricsResponse(BaseModel):
    depth: int
    pending: int
    dlq_depth: int


@router.get("/metrics", response_model=QueueMetricsResponse)
async def queue_metrics(queue: RedisStreamQueue = Depends(get_queue)) -> QueueMetricsResponse:
    return QueueMetricsResponse(
        depth=await queue.depth(),
        pending=await queue.pending_count(),
        dlq_depth=await queue.dlq_depth(),
    )
