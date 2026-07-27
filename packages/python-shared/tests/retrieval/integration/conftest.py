"""Real Postgres + pgvector fixtures for the retrieval SQL.

The unit tests use an in-memory `ChunkSearchPort` fake, so the actual
`WHERE workspace_id = ...` / `ORDER BY embedding <=> ...` SQL — the only
place where cross-tenant leakage can physically happen — would otherwise
never execute. That is exactly what a fake cannot prove (CLAUDE.md §11).

Skips (never silently passes) when `AGENTVERSE_SHARED_DATABASE_URL` is
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

_DATABASE_URL = os.environ.get("AGENTVERSE_SHARED_DATABASE_URL")

DIM = 1536
MODEL = "text-embedding-3-small"
VERSION = "1"


def vector_literal(seed: float, *, second: float = 1.0) -> list[float]:
    v = [0.0] * DIM
    v[0] = seed
    v[1] = second
    return v


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    if not _DATABASE_URL:
        pytest.skip("AGENTVERSE_SHARED_DATABASE_URL not set — needs a real Postgres")
    engine = create_async_engine(_DATABASE_URL, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def seeded(db_session: AsyncSession) -> AsyncIterator[dict[str, str]]:
    """Two workspaces, each with a knowledge base and a document, so
    cross-tenant assertions have a real second tenant to be isolated
    from rather than asserting against an empty table.
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
        "doc_a2": str(uuid.uuid4()),
        "doc_b": str(uuid.uuid4()),
    }

    await db_session.execute(
        text(
            "INSERT INTO users (id, email, name, email_verified, created_at, updated_at) "
            "VALUES (:id, :email, 'retrieval-int', false, :now, :now)"
        ),
        {"id": user_id, "email": f"{user_id}@example.test", "now": now},
    )
    for ws_key in ("ws_a", "ws_b"):
        await db_session.execute(
            text(
                "INSERT INTO workspaces (id, name, slug, created_at) "
                "VALUES (:id, :name, :name, :now)"
            ),
            {"id": ids[ws_key], "name": f"ws-{ids[ws_key][:8]}", "now": now},
        )
    for kb_key, ws_key in (("kb_a", "ws_a"), ("kb_b", "ws_b")):
        await db_session.execute(
            text(
                "INSERT INTO knowledge_bases "
                "(id, workspace_id, name, embedding_model, embedding_model_version, "
                " created_by_user_id, created_at, updated_at) "
                "VALUES (:id, :ws, :name, :model, :version, :user, :now, :now)"
            ),
            {
                "id": ids[kb_key],
                "ws": ids[ws_key],
                "name": f"kb-{kb_key}",
                "model": MODEL,
                "version": VERSION,
                "user": user_id,
                "now": now,
            },
        )
    for doc_key, kb_key, ws_key in (
        ("doc_a", "kb_a", "ws_a"),
        ("doc_a2", "kb_a", "ws_a"),
        ("doc_b", "kb_b", "ws_b"),
    ):
        await db_session.execute(
            text(
                "INSERT INTO kb_documents "
                "(id, workspace_id, knowledge_base_id, storage_key, original_filename, "
                " content_type, size_bytes, content_hash, status, chunk_count, "
                " created_at, updated_at) "
                "VALUES (:id, :ws, :kb, :key, 'notes.txt', 'text/plain', 10, '', "
                "        'indexed', 0, :now, :now)"
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

    await db_session.execute(
        text("DELETE FROM workspaces WHERE id = ANY(:ids)"),
        {"ids": [ids["ws_a"], ids["ws_b"]]},
    )
    await db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    await db_session.commit()


async def insert_chunk(
    session: AsyncSession,
    *,
    workspace_id: str,
    kb_id: str,
    document_id: str,
    content: str,
    embedding: list[float],
    index: int = 0,
    model: str = MODEL,
    version: str = VERSION,
) -> str:
    chunk_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO kb_chunks "
            "(id, workspace_id, knowledge_base_id, kb_document_id, chunk_index, content, "
            " token_count, embedding, embedding_model, embedding_model_version, "
            " content_hash, created_at) "
            "VALUES (:id, :ws, :kb, :doc, :index, :content, :tokens, "
            "        CAST(:embedding AS vector), :model, :version, :hash, now())"
        ),
        {
            "id": chunk_id,
            "ws": workspace_id,
            "kb": kb_id,
            "doc": document_id,
            "index": index,
            "content": content,
            "tokens": len(content.split()),
            "embedding": "[" + ",".join(repr(float(x)) for x in embedding) + "]",
            "model": model,
            "version": version,
            "hash": chunk_id,
        },
    )
    await session.commit()
    return chunk_id
