"""Liveness and readiness routes (CLAUDE.md §5)."""

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis

from agentverse_worker.interface.dependencies import get_redis_client
from agentverse_worker.interface.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness: is the process up at all."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
async def ready(
    response: Response, redis_client: Redis = Depends(get_redis_client)
) -> HealthResponse:
    """Readiness: Redis — the job queue's hard dependency — must be
    reachable (docs/systems/health-checks.md: "Phase 3: apps/worker's
    /ready gains a real Redis connectivity check").
    """
    try:
        await redis_client.ping()
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="unavailable")
    return HealthResponse(status="ok")
