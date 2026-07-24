"""Liveness and readiness routes.

Every new service defines `/health` and `/ready` before any business
route (CLAUDE.md §5). This router ships before any other in Phase 0
because there is no business route yet.
"""

from fastapi import APIRouter

from agentverse_api.interface.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness: is the process up and serving requests at all."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
async def ready() -> HealthResponse:
    """Readiness: are hard dependencies reachable.

    No dependency (Postgres/Redis/vector DB) is consumed by any code
    path yet in Phase 0, so readiness currently reduces to liveness.
    Phase 1 adds a real Postgres connectivity check here.
    """
    return HealthResponse(status="ok")
