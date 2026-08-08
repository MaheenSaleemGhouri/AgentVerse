"""The assistant use case: retrieve, assemble, stream, persist.

One provider call per turn, with no tool loop. That is the whole design,
and it is a deliberate ceiling rather than a stage of something larger:
the assistant answers questions about the product from the product's own
documentation. It cannot create an agent, start a run, or change a
setting — so there is nothing for it to call, no loop to bound, and no
class of action that needs an allow/deny policy check (CLAUDE.md §4,
Human Approval). If it ever grows the ability to act, that is a new
design with an ADR, not a parameter added here.

Every database touch is its own short transaction. The alternative — one
request-scoped session — would hold a pooled connection open across the
whole streamed generation, which CLAUDE.md §7 forbids for exactly the
reason it would bite here: a few dozen concurrent help questions would
exhaust the pool while doing no database work at all.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from agentverse_shared.cost_accounting import calculate_cost_micro_usd

from agentverse_api.assistant_service.domain import prompt
from agentverse_api.assistant_service.domain.entities import (
    MAX_ANSWER_TOKENS,
    MAX_PASSAGES,
    AssistantMessage,
    AssistantSession,
)
from agentverse_api.assistant_service.domain.ports import DocsIndex, UnitOfWork
from agentverse_api.orchestration_service.domain.entities import (
    ChatRequest,
    StreamDelta,
    StreamDone,
    StreamError,
    StreamEvent,
)
from agentverse_api.orchestration_service.domain.ports.provider_adapter import ProviderAdapter

logger = logging.getLogger(__name__)

ASSISTANT_MODEL = "gpt-4o-mini"
"""Routed cheap on purpose (CLAUDE.md §4, Cost Optimization). This is
extractive question-answering over four short passages already present
in the prompt — the reasoning is shallow, and the strongest model would
buy nothing but latency and cost on every help question asked."""

MAX_SESSIONS_LISTED = 30


class SessionNotFoundError(LookupError):
    """No such session *for this workspace and user*. The route answers
    404 without distinguishing "does not exist" from "not yours" —
    Rule 11's no-leak rule applies to a colleague's session as much as to
    another tenant's."""


class AssistantService:
    def __init__(
        self, *, unit_of_work: UnitOfWork, docs: DocsIndex, adapter: ProviderAdapter
    ) -> None:
        self._uow = unit_of_work
        self._docs = docs
        self._adapter = adapter

    async def start_session(
        self, *, workspace_id: str, user_id: str, first_question: str
    ) -> AssistantSession:
        async with self._uow() as sessions:
            return await sessions.create_session(
                workspace_id=workspace_id,
                user_id=user_id,
                title=prompt.title_from(first_question),
            )

    async def list_sessions(self, *, workspace_id: str, user_id: str) -> list[AssistantSession]:
        async with self._uow() as sessions:
            return await sessions.list_sessions(
                workspace_id=workspace_id, user_id=user_id, limit=MAX_SESSIONS_LISTED
            )

    async def ensure_session(self, *, workspace_id: str, user_id: str, session_id: str) -> None:
        """Raises `SessionNotFoundError` unless the session is this
        user's, in this workspace.

        Exposed so a route can decide its 404 *before* opening a stream —
        an SSE body cannot change its own status code, and an error frame
        inside a 200 is a worse contract than a real 404. `answer` still
        checks for itself; this is a convenience, not the enforcement
        point.
        """
        async with self._uow() as sessions:
            if (
                await sessions.get_session(
                    workspace_id=workspace_id, user_id=user_id, session_id=session_id
                )
                is None
            ):
                raise SessionNotFoundError(session_id)

    async def history(
        self, *, workspace_id: str, user_id: str, session_id: str
    ) -> list[AssistantMessage]:
        async with self._uow() as sessions:
            found = await sessions.get_session(
                workspace_id=workspace_id, user_id=user_id, session_id=session_id
            )
            if found is None:
                raise SessionNotFoundError(session_id)
            return await sessions.list_messages(session_id=session_id)

    async def answer(
        self, *, workspace_id: str, user_id: str, session_id: str, question: str
    ) -> AsyncIterator[StreamEvent]:
        """Streams one answer, persisting both turns.

        The user's message is committed *before* the provider call, so a
        provider failure still leaves a conversation showing what was
        asked. Writing both at the end would swallow the question along
        with the error.

        The assistant's message is written only on `StreamDone`. A turn
        that ended in `StreamError` has no answer to store, and storing
        the partial text would put words in the assistant's mouth that it
        never finished saying — and then feed them back as history on the
        next question.
        """
        async with self._uow() as sessions:
            found = await sessions.get_session(
                workspace_id=workspace_id, user_id=user_id, session_id=session_id
            )
            if found is None:
                raise SessionNotFoundError(session_id)
            history = await sessions.list_messages(session_id=session_id)
            await sessions.append_message(session_id=session_id, role="user", content=question)

        passages = self._docs.search(question, limit=MAX_PASSAGES)
        request = ChatRequest(
            model=ASSISTANT_MODEL,
            messages=prompt.build(question=question, history=history, passages=passages),
            max_output_tokens=MAX_ANSWER_TOKENS,
        )

        answer: list[str] = []
        async for event in self._adapter.stream_chat(request):
            if isinstance(event, StreamDelta):
                answer.append(event.text)
            elif isinstance(event, StreamDone):
                async with self._uow() as sessions:
                    await sessions.append_message(
                        session_id=session_id, role="assistant", content="".join(answer)
                    )
                logger.info(
                    "assistant_answer workspace_id=%s session_id=%s passages=%d "
                    "prompt_tokens=%d completion_tokens=%d cost_micro_usd=%d",
                    workspace_id,
                    session_id,
                    len(passages),
                    event.usage.prompt_tokens,
                    event.usage.completion_tokens,
                    calculate_cost_micro_usd(ASSISTANT_MODEL, event.usage),
                )
            elif isinstance(event, StreamError):
                logger.warning(
                    "assistant_answer_failed workspace_id=%s session_id=%s code=%s",
                    workspace_id,
                    session_id,
                    event.code,
                )
            yield event
