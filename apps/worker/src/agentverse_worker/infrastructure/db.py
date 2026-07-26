"""Async Postgres engine/session — the only place a connection pool is
created (CLAUDE.md §7: config loaded once, not scattered).

Unlike apps/api's `get_db_session` (a FastAPI per-request dependency),
this service has no request/response cycle around a session — a job
handler owns its session for the duration of one job, so this exposes
an async context manager instead of a generator dependency. Same
commit-on-success/rollback-on-exception discipline either way.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from agentverse_worker.infrastructure.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(settings.database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """One session per call: `async with get_session() as session: ...`."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
