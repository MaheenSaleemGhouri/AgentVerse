"""Async Postgres engine/session — the only place a connection pool is
created (CLAUDE.md §7: config loaded once, not scattered).

A transaction is never held open across an LLM/external call (CLAUDE.md
§7) — not a concern yet in Phase 1 since no route calls out to an LLM,
but `get_db_session`'s per-request scope is what keeps that true later:
each request gets its own session, committed/rolled back and closed
before the response returns.
"""

import json
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from agentverse_api.infrastructure.config import get_settings


def _json_serializer(obj: Any) -> str:
    # Defense-in-depth for JSONB columns: a raw `uuid.UUID` (or other
    # non-JSON-native value) reaching here is a bug at its source — the
    # `agentverse_shared.retrieval.postgres_search` rows this service
    # shares with apps/worker must `str()` UUID columns themselves,
    # since raw `text()` queries return native `uuid.UUID` objects — but
    # the default `json.dumps` raises `TypeError` and fails the whole
    # request; `default=str` degrades that to a readable value instead.
    return json.dumps(obj, default=str)


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url, pool_pre_ping=True, json_serializer=_json_serializer
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, committed on success."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
