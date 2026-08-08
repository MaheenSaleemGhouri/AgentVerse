"""Ports the assistant depends on. Implemented in `infrastructure/`."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol

from agentverse_api.assistant_service.domain.entities import (
    AssistantMessage,
    AssistantRole,
    AssistantSession,
    DocPassage,
)


class DocsIndex(Protocol):
    """Retrieval over the published guides.

    A port rather than a direct dependency because the corpus is small
    enough today that term-overlap scoring beats embeddings on both
    latency and cost — but that is a property of eleven guides, not a
    permanent truth. When the corpus outgrows it, a vector-backed
    implementation swaps in here and the application layer does not move.
    """

    def search(self, query: str, *, limit: int) -> list[DocPassage]: ...


class AssistantSessionRepository(Protocol):
    async def create_session(
        self, *, workspace_id: str, user_id: str, title: str
    ) -> AssistantSession: ...

    async def get_session(
        self, *, workspace_id: str, user_id: str, session_id: str
    ) -> AssistantSession | None:
        """Scoped by workspace *and* user in the query itself, not checked
        after the fetch — the difference between a filter and an assertion
        is the difference between isolation and a bug waiting for someone
        to forget the assertion (CLAUDE.md Rule 11)."""
        ...

    async def list_sessions(
        self, *, workspace_id: str, user_id: str, limit: int
    ) -> list[AssistantSession]: ...

    async def list_messages(self, *, session_id: str) -> list[AssistantMessage]: ...

    async def append_message(
        self, *, session_id: str, role: AssistantRole, content: str
    ) -> AssistantMessage: ...


class UnitOfWork(Protocol):
    """Opens one short transaction and commits it on exit.

    The assistant takes this rather than a session-bound repository
    because it writes *around* a streaming provider call, and CLAUDE.md
    §7 forbids holding a transaction open across an external call — a
    request-scoped session would sit idle in the pool for the whole
    generation, starving it under any real concurrency.
    """

    def __call__(self) -> AbstractAsyncContextManager[AssistantSessionRepository]: ...
