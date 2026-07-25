"""Integration test fixtures — real Postgres, never mocked (CLAUDE.md §11).

Skips the whole suite if `AGENTVERSE_API_DATABASE_URL` isn't set, rather
than silently falling back to something that isn't a real database.
Each test uses a fresh, randomly-suffixed workspace name (`unique_name`)
so tests can run against a shared, persistent dev/CI Postgres without
needing savepoint-based rollback isolation — the target Postgres in CI
is a fresh container per run anyway.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

pytestmark = pytest.mark.integration

_DATABASE_URL = os.environ.get("AGENTVERSE_API_DATABASE_URL")


def _require_database_url() -> str:
    if not _DATABASE_URL:
        pytest.skip("AGENTVERSE_API_DATABASE_URL not set — integration tests need a real Postgres")
    return _DATABASE_URL


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    # Function-scoped, not session-scoped: pytest-asyncio's default
    # "auto" mode gives each test its own event loop, and an async
    # engine's connection pool is bound to whichever loop was running
    # when it was created — a session-scoped engine gets reused across
    # later tests' *different* loops, which fails with "Future attached
    # to a different loop" (confirmed by actually running this suite).
    engine = create_async_engine(_require_database_url(), pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
def unique_name() -> str:
    return f"test-{uuid.uuid4().hex[:12]}"
