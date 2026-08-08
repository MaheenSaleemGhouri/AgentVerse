"""`/api/v1/workspaces/{workspace_id}/assistant` — the in-product help
assistant.

Gated by `require_viewer`, not `require_member`. The assistant costs a
provider call, so gating it higher is tempting, but a viewer is the role
most likely to be new and most likely to need "where do I find X" — and
the same answer is already free to read at `/docs`. Spend is bounded
instead by the per-workspace rate limit at the gateway and by
`MAX_ANSWER_TOKENS`, which is where a cost ceiling belongs.

`workspace_id` comes from the resolved `WorkspaceContext`, never from the
path string (Rule 6), and so does `user_id` — a session is personal, and
reading it is scoped to its owner in the query itself.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from agentverse_api.assistant_service.application.assistant_service import (
    AssistantService,
    SessionNotFoundError,
)
from agentverse_api.assistant_service.interface.dependencies.services import (
    get_assistant_service,
)
from agentverse_api.assistant_service.interface.schemas.assistant import (
    AskRequest,
    MessageResponse,
    SessionResponse,
)
from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import require_viewer
from agentverse_api.orchestration_service.domain.entities import (
    StreamDelta,
    StreamDone,
    StreamEvent,
)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/assistant",
    tags=["assistant"],
)


def _serialize(event: StreamEvent) -> str:
    """One provider stream event -> one SSE frame.

    Exhaustive over the union, matching `internal_provider_test`'s frame
    shape so the frontend has one event contract to handle rather than
    two that drift.
    """
    payload: dict[str, str | int | None]
    if isinstance(event, StreamDelta):
        payload = {"type": "delta", "text": event.text}
    elif isinstance(event, StreamDone):
        payload = {"type": "done", "finish_reason": event.finish_reason}
    else:
        payload = {"type": "error", "code": event.code, "message": event.message}
    return f"data: {json.dumps(payload)}\n\n"


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions_route(
    context: WorkspaceContext = Depends(require_viewer),
    service: AssistantService = Depends(get_assistant_service),
) -> list[SessionResponse]:
    """Your own recent conversations in this workspace, newest first."""
    sessions = await service.list_sessions(
        workspace_id=context.workspace_id, user_id=context.user_id
    )
    return [
        SessionResponse(
            id=session.id,
            title=session.title,
            created_at=session.created_at,
            last_message_at=session.last_message_at,
        )
        for session in sessions
    ]


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session_route(
    body: AskRequest,
    context: WorkspaceContext = Depends(require_viewer),
    service: AssistantService = Depends(get_assistant_service),
) -> SessionResponse:
    """Opens a conversation titled from its first question.

    Takes the question but does not answer it: creating the session and
    streaming the answer are separate calls because SSE cannot carry a
    created resource's id back to the client before the body starts.
    """
    session = await service.start_session(
        workspace_id=context.workspace_id,
        user_id=context.user_id,
        first_question=body.question,
    )
    return SessionResponse(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        last_message_at=session.last_message_at,
    )


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def list_messages_route(
    session_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    service: AssistantService = Depends(get_assistant_service),
) -> list[MessageResponse]:
    try:
        messages = await service.history(
            workspace_id=context.workspace_id,
            user_id=context.user_id,
            session_id=session_id,
        )
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such session"
        ) from exc

    return [
        MessageResponse(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )
        for message in messages
    ]


@router.post("/sessions/{session_id}/messages")
async def ask_route(
    session_id: str,
    body: AskRequest,
    context: WorkspaceContext = Depends(require_viewer),
    service: AssistantService = Depends(get_assistant_service),
) -> StreamingResponse:
    """Asks a question and streams the answer as SSE.

    The session is resolved before the response starts, so a 404 is a
    real 404 rather than an error frame inside a 200 stream.
    """
    try:
        await service.ensure_session(
            workspace_id=context.workspace_id,
            user_id=context.user_id,
            session_id=session_id,
        )
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such session"
        ) from exc

    async def _frames() -> AsyncIterator[str]:
        async for event in service.answer(
            workspace_id=context.workspace_id,
            user_id=context.user_id,
            session_id=session_id,
            question=body.question.strip(),
        ):
            yield _serialize(event)

    return StreamingResponse(
        _frames(),
        media_type="text/event-stream",
        # Streaming responses must never be cached — CLAUDE.md §12 says
        # so for the CDN, and an intermediary buffering this one would
        # turn a live answer into a long blank pause.
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
