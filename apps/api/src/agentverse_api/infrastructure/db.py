"""Async Postgres engine/session — the only place a connection pool is
created (CLAUDE.md §7: config loaded once, not scattered).

A transaction is never held open across an LLM/external call (CLAUDE.md
§7) — not a concern yet in Phase 1 since no route calls out to an LLM,
but `get_db_session`'s per-request scope is what keeps that true later:
each request gets its own session, committed/rolled back and closed
before the response returns.
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from agentverse_api.infrastructure.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(settings.database_url, pool_pre_ping=True)


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
