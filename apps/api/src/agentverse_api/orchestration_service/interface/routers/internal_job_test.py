"""`/internal/job-test` — submits a trivial echo job onto apps/worker's
Redis Streams queue for verification (docs/roadmap.md Phase 3
acceptance criteria). Not part of the public `/api/v1` surface;
protected by the same shared-secret check as `/internal/auth-events`
and `/internal/provider-test` (CLAUDE.md §10 zero trust).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agentverse_api.auth_service.interface.dependencies.internal_service_auth import (
    require_internal_service,
)
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_job_queue_producer,
)
from agentverse_api.orchestration_service.interface.schemas.job_test import (
    JobTestRequest,
    JobTestResponse,
)

router = APIRouter(
    prefix="/internal/job-test",
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
)


@router.post("/enqueue", response_model=JobTestResponse)
async def enqueue_echo_job(
    body: JobTestRequest,
    producer: JobQueueProducer = Depends(get_job_queue_producer),
) -> JobTestResponse:
    payload = {**body.payload, "force_fail": body.force_fail}
    job_id, stream_id = await producer.enqueue_echo_job(payload, max_attempts=body.max_attempts)
    return JobTestResponse(job_id=job_id, stream_id=stream_id)
