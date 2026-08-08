"""The use case, against fakes — no provider call, no database."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from agentverse_api.assistant_service.application.assistant_service import (
    AssistantService,
    SessionNotFoundError,
)
from agentverse_api.assistant_service.domain.entities import (
    AssistantMessage,
    AssistantRole,
    AssistantSession,
    DocPassage,
)
from agentverse_api.assistant_service.domain.ports import AssistantSessionRepository
from agentverse_api.orchestration_service.domain.entities import (
    StreamDelta,
    StreamDone,
    StreamError,
    TokenUsage,
)
from tests.fakes.provider_adapter import FakeProviderAdapter

WORKSPACE = "ws-1"
OTHER_WORKSPACE = "ws-2"
USER = "user-1"
OTHER_USER = "user-2"


@dataclass
class FakeSessions:
    """In-memory `AssistantSessionRepository`.

    Scoping is enforced in the lookup, exactly as the SQL repository does
    it — a fake that checks after fetching would let a real isolation bug
    through the test that exists to catch it.
    """

    sessions: dict[str, AssistantSession] = field(default_factory=dict)
    messages: dict[str, list[AssistantMessage]] = field(default_factory=dict)
    commits: int = 0

    async def create_session(
        self, *, workspace_id: str, user_id: str, title: str
    ) -> AssistantSession:
        now = datetime.now(UTC)
        session = AssistantSession(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            user_id=user_id,
            title=title,
            created_at=now,
            last_message_at=now,
        )
        self.sessions[session.id] = session
        self.messages[session.id] = []
        return session

    async def get_session(
        self, *, workspace_id: str, user_id: str, session_id: str
    ) -> AssistantSession | None:
        found = self.sessions.get(session_id)
        if found is None or found.workspace_id != workspace_id or found.user_id != user_id:
            return None
        return found

    async def list_sessions(
        self, *, workspace_id: str, user_id: str, limit: int
    ) -> list[AssistantSession]:
        return [
            session
            for session in self.sessions.values()
            if session.workspace_id == workspace_id and session.user_id == user_id
        ][:limit]

    async def list_messages(self, *, session_id: str) -> list[AssistantMessage]:
        return list(self.messages.get(session_id, []))

    async def append_message(
        self, *, session_id: str, role: AssistantRole, content: str
    ) -> AssistantMessage:
        message = AssistantMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            created_at=datetime.now(UTC),
        )
        self.messages.setdefault(session_id, []).append(message)
        return message


@dataclass
class FakeDocs:
    passages: list[DocPassage] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)

    def search(self, query: str, *, limit: int) -> list[DocPassage]:
        self.queries.append(query)
        return self.passages[:limit]


def build(
    *, events: list[object] | None = None, passages: list[DocPassage] | None = None
) -> tuple[AssistantService, FakeSessions, FakeProviderAdapter]:
    repo = FakeSessions()
    adapter = FakeProviderAdapter(stream_events=list(events or []))  # type: ignore[arg-type]

    @asynccontextmanager
    async def unit_of_work() -> AsyncIterator[AssistantSessionRepository]:
        repo.commits += 1
        yield repo

    service = AssistantService(
        unit_of_work=unit_of_work, docs=FakeDocs(passages or []), adapter=adapter
    )
    return service, repo, adapter


DONE = StreamDone(finish_reason="stop", usage=TokenUsage(prompt_tokens=10, completion_tokens=5))


async def drain(service: AssistantService, session_id: str, question: str = "how?") -> None:
    async for _ in service.answer(
        workspace_id=WORKSPACE, user_id=USER, session_id=session_id, question=question
    ):
        pass


async def test_a_session_is_titled_from_its_first_question() -> None:
    service, _, _ = build()

    session = await service.start_session(
        workspace_id=WORKSPACE, user_id=USER, first_question="  How do   I sign a webhook? "
    )

    assert session.title == "How do I sign a webhook?"


async def test_both_turns_are_persisted_on_a_successful_answer() -> None:
    service, repo, _ = build(events=[StreamDelta(text="Use "), StreamDelta(text="HMAC."), DONE])
    session = await service.start_session(workspace_id=WORKSPACE, user_id=USER, first_question="q")

    await drain(service, session.id, "how do I sign?")

    assert [(m.role, m.content) for m in repo.messages[session.id]] == [
        ("user", "how do I sign?"),
        ("assistant", "Use HMAC."),
    ]


async def test_a_failed_answer_still_records_the_question() -> None:
    """A provider failure that swallowed the question too would leave a
    conversation with a gap where the user's own words should be."""
    service, repo, _ = build(
        events=[StreamError(code="rate_limited", message="slow down", retry_after_seconds=1)]
    )
    session = await service.start_session(workspace_id=WORKSPACE, user_id=USER, first_question="q")

    await drain(service, session.id, "how do I sign?")

    assert [(m.role, m.content) for m in repo.messages[session.id]] == [("user", "how do I sign?")]


async def test_a_partial_answer_is_not_stored() -> None:
    """Storing it would put words in the assistant's mouth it never
    finished saying — and feed them back as history next turn."""
    service, repo, _ = build(
        events=[
            StreamDelta(text="Use HM"),
            StreamError(code="provider_error", message="dropped", retry_after_seconds=None),
        ]
    )
    session = await service.start_session(workspace_id=WORKSPACE, user_id=USER, first_question="q")

    await drain(service, session.id)

    assert [m.role for m in repo.messages[session.id]] == ["user"]


async def test_the_prior_turn_is_context_but_the_new_question_is_not_duplicated() -> None:
    service, _, adapter = build(events=[StreamDelta(text="a"), DONE])
    session = await service.start_session(workspace_id=WORKSPACE, user_id=USER, first_question="q")

    await drain(service, session.id, "first")
    await drain(service, session.id, "second")

    contents = [message.content for message in adapter.requests[-1].messages]
    assert contents.count("second") == 1
    assert "first" in contents


async def test_the_answer_is_bounded() -> None:
    """CLAUDE.md Rule 17 — the cost ceiling is set here, not left to the
    provider's default."""
    service, _, adapter = build(events=[DONE])
    session = await service.start_session(workspace_id=WORKSPACE, user_id=USER, first_question="q")

    await drain(service, session.id)

    assert adapter.requests[-1].max_output_tokens == 800


@pytest.mark.parametrize(
    ("workspace_id", "user_id"),
    [
        (OTHER_WORKSPACE, USER),  # another tenant
        (WORKSPACE, OTHER_USER),  # a colleague in the same workspace
    ],
)
async def test_a_session_is_invisible_outside_its_workspace_and_owner(
    workspace_id: str, user_id: str
) -> None:
    service, _, adapter = build(events=[DONE])
    session = await service.start_session(workspace_id=WORKSPACE, user_id=USER, first_question="q")

    with pytest.raises(SessionNotFoundError):
        await service.history(workspace_id=workspace_id, user_id=user_id, session_id=session.id)

    with pytest.raises(SessionNotFoundError):
        await service.ensure_session(
            workspace_id=workspace_id, user_id=user_id, session_id=session.id
        )

    # And no provider call was made on the way to finding out.
    assert adapter.requests == []


async def test_answering_an_unknown_session_never_reaches_the_provider() -> None:
    service, _, adapter = build(events=[DONE])

    with pytest.raises(SessionNotFoundError):
        async for _ in service.answer(
            workspace_id=WORKSPACE, user_id=USER, session_id=str(uuid.uuid4()), question="q"
        ):
            pass

    assert adapter.requests == []
