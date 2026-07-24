"""Liveness and readiness routes (CLAUDE.md §5)."""

from fastapi import APIRouter

from agentverse_worker.interface.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness: is the process up at all."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
async def ready() -> HealthResponse:
    """Readiness: are hard dependencies reachable.

    No queue consumer exists yet in Phase 0, so there is no Redis
    connection to check. Phase 3 adds a real Redis connectivity check
    here once this service actually consumes jobs from a queue.
    """
    return HealthResponse(status="ok")
