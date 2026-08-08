"""Integration fixtures — real Postgres, never mocked (CLAUDE.md §11).

Mirrors the search/marketplace integration conftests: skips rather than
falling back to something that is not a real database, and takes a
function-scoped engine because pytest-asyncio gives each test its own
event loop.

The thing under test here is isolation, and isolation is enforced by the
`WHERE` clause of a real query. A faked repository would assert only
that the fake filters the way the test told it to.
"""

from __future__ import annotations

import os
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
    engine = create_async_engine(_require_database_url(), pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
