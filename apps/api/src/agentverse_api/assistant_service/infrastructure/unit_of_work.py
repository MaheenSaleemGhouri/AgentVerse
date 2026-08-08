"""`UnitOfWork` over the shared session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from agentverse_api.assistant_service.domain.ports import AssistantSessionRepository
from agentverse_api.assistant_service.infrastructure.repositories import (
    SqlAssistantSessionRepository,
)
from agentverse_api.infrastructure.db import get_session_factory


@asynccontextmanager
async def sql_unit_of_work() -> AsyncIterator[AssistantSessionRepository]:
    """One session, one transaction, committed on clean exit.

    Mirrors `get_db_session`'s contract deliberately — same commit-on-
    success, rollback-on-exception behaviour — but scoped to a block
    instead of a request, because the assistant's writes bracket a
    streaming provider call that must not sit inside a transaction.
    """
    async with get_session_factory()() as session:
        try:
            yield SqlAssistantSessionRepository(session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
