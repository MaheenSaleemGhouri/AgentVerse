"""`/internal/provider-test` — proves `ProviderAdapter.stream_chat` works
end-to-end, with no agent/run/worker concept involved (roadmap Phase 2
Features). Not part of the public `/api/v1` surface; protected by the
same shared-secret check as `/internal/auth-events` (CLAUDE.md §10 zero
trust: the internal network boundary alone is not sufficient
authorization).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from agentverse_api.auth_service.interface.dependencies.internal_service_auth import (
    require_internal_service,
)
from agentverse_api.orchestration_service.application.provider_test_service import (
    ProviderTestService,
)
from agentverse_api.orchestration_service.domain.entities import (
    StreamDelta,
    StreamDone,
    StreamEvent,
)
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_provider_test_service,
)
from agentverse_api.orchestration_service.interface.schemas.provider_test import (
    ProviderTestRequest,
)

router = APIRouter(
    prefix="/internal/provider-test",
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
)


def _serialize(event: StreamEvent) -> str:
    """One `ProviderAdapter.StreamEvent` -> one SSE frame. Exhaustive over
    the union so a new event variant fails loudly here instead of
    silently dropping data (mirrors the frontend's exhaustive SSE handler
    discipline, CLAUDE.md §6).
    """
    payload: dict[str, str | int | float | None]
    if isinstance(event, StreamDelta):
        payload = {"type": "delta", "text": event.text}
    elif isinstance(event, StreamDone):
        payload = {
            "type": "done",
            "finish_reason": event.finish_reason,
            "prompt_tokens": event.usage.prompt_tokens,
            "completion_tokens": event.usage.completion_tokens,
        }
    else:
        payload = {
            "type": "error",
            "code": event.code,
            "message": event.message,
            "retry_after_seconds": event.retry_after_seconds,
        }
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/stream")
async def stream_provider_test(
    body: ProviderTestRequest,
    service: ProviderTestService = Depends(get_provider_test_service),
) -> StreamingResponse:
    async def _frames() -> AsyncIterator[str]:
        async for event in service.stream_completion(prompt=body.prompt, model=body.model):
            yield _serialize(event)

    return StreamingResponse(_frames(), media_type="text/event-stream")
