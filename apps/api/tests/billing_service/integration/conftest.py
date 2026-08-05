"""Integration fixtures — real Postgres, never mocked (CLAUDE.md §11).

Mirrors `tests/auth_service/integration/conftest.py`: skips rather than
falling back to something that is not a real database, and takes a
function-scoped engine because pytest-asyncio gives each test its own
event loop.

The catalog assertions below are the reason these are integration tests
at all: the seed rows live in a migration, so a fake repository would
prove nothing about whether the shipped catalog actually parses.
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
