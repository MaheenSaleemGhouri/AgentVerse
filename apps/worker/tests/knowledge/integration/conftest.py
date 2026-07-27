"""Integration fixtures — real Postgres with real pgvector, never mocked
(CLAUDE.md §11).

The unit tests for the ingestion job use an in-memory fake repository, so
`WorkerKnowledgeRepository` itself — the SQLAlchemy Core code that writes
actual `vector(1536)` values and relies on a real `ON CONFLICT` clause —
would otherwise never execute. That is precisely the code a fake cannot
prove correct.

Skips (never silently passes) when `AGENTVERSE_WORKER_DATABASE_URL` is
unset.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

pytestmark = pytest.mark.integration

_DATABASE_URL = os.environ.get("AGENTVERSE_WORKER_DATABASE_URL")


def _require_database_url() -> str:
    if not _DATABASE_URL:
        pytest.skip(
            "AGENTVERSE_WORKER_DATABASE_URL not set — integration tests need a real Postgres"
        )
    return _DATABASE_URL


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    # Function-scoped for the same reason as apps/api's equivalent: an
    # async engine's pool binds to the loop that created it, and
    # pytest-asyncio gives each test its own loop.
    engine = create_async_engine(_require_database_url(), pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def seeded(db_session: AsyncSession) -> AsyncIterator[dict[str, str]]:
    """Creates two workspaces, each with its own knowledge base and
    document, so cross-tenant assertions have a real second tenant to be
    isolated from rather than asserting against an empty table.
    """
    now = datetime.now(UTC)
    user_id = str(uuid.uuid4())
    ids = {
        "user_id": user_id,
        "ws_a": str(uuid.uuid4()),
        "ws_b": str(uuid.uuid4()),
        "kb_a": str(uuid.uuid4()),
        "kb_b": str(uuid.uuid4()),
        "doc_a": str(uuid.uuid4()),
        "doc_b": str(uuid.uuid4()),
    }

    await db_session.execute(
        text(
            "INSERT INTO users (id, email, name, email_verified, created_at, updated_at) "
            "VALUES (:id, :email, :name, false, :now, :now)"
        ),
        {"id": user_id, "email": f"{user_id}@example.test", "name": "kb-int", "now": now},
    )
    for ws_key in ("ws_a", "ws_b"):
        await db_session.execute(
            text(
                "INSERT INTO workspaces (id, name, slug, created_at) "
                "VALUES (:id, :name, :slug, :now)"
            ),
            {
                "id": ids[ws_key],
                "name": f"ws-{ids[ws_key][:8]}",
                "slug": f"ws-{ids[ws_key][:8]}",
                "now": now,
            },
        )
    for kb_key, ws_key in (("kb_a", "ws_a"), ("kb_b", "ws_b")):
        await db_session.execute(
            text(
                "INSERT INTO knowledge_bases "
                "(id, workspace_id, name, embedding_model, embedding_model_version, "
                " created_by_user_id, created_at, updated_at) "
                "VALUES (:id, :ws, :name, 'text-embedding-3-small', '1', :user, :now, :now)"
            ),
            {
                "id": ids[kb_key],
                "ws": ids[ws_key],
                "name": f"kb-{kb_key}",
                "user": user_id,
                "now": now,
            },
        )
    for doc_key, kb_key, ws_key in (("doc_a", "kb_a", "ws_a"), ("doc_b", "kb_b", "ws_b")):
        await db_session.execute(
            text(
                "INSERT INTO kb_documents "
                "(id, workspace_id, knowledge_base_id, storage_key, original_filename, "
                " content_type, size_bytes, content_hash, status, chunk_count, "
                " created_at, updated_at) "
                "VALUES (:id, :ws, :kb, :key, 'notes.txt', 'text/plain', 10, '', "
                "        'pending', 0, :now, :now)"
            ),
            {
                "id": ids[doc_key],
                "ws": ids[ws_key],
                "kb": ids[kb_key],
                "key": f"{ids[ws_key]}/{uuid.uuid4()}.txt",
                "now": now,
            },
        )
    await db_session.commit()

    yield ids

    # Workspaces cascade to knowledge_bases → kb_documents → kb_chunks.
    await db_session.execute(
        text("DELETE FROM workspaces WHERE id = ANY(:ids)"),
        {"ids": [ids["ws_a"], ids["ws_b"]]},
    )
    await db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    await db_session.commit()
