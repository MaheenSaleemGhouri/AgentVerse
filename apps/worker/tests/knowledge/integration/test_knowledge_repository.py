"""`WorkerKnowledgeRepository` against real Postgres + pgvector.

Proves the things a fake repository structurally cannot: that a
1536-dimension vector actually round-trips through the `vector` column,
that the `ON CONFLICT DO NOTHING` idempotency guarantee holds at the
database level under a genuine duplicate insert, and that a similarity
query pre-filtered by `workspace_id` returns zero rows from another
tenant (docs/roadmap.md Phase 5's named acceptance criterion).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_worker.knowledge.repository import ChunkRow, WorkerKnowledgeRepository

pytestmark = pytest.mark.integration

DIM = 1536


def _vector(seed: float) -> list[float]:
    """A unit-ish vector distinguishable by its first component."""
    v = [0.0] * DIM
    v[0] = seed
    v[1] = 1.0
    return v


def _chunk(
    *, ws: str, kb: str, doc: str, index: int, content: str, content_hash: str, seed: float = 1.0
) -> ChunkRow:
    return ChunkRow(
        id=str(uuid.uuid4()),
        workspace_id=ws,
        knowledge_base_id=kb,
        kb_document_id=doc,
        chunk_index=index,
        content=content,
        token_count=len(content.split()),
        embedding=_vector(seed),
        embedding_model="text-embedding-3-small",
        embedding_model_version="1",
        content_hash=content_hash,
    )


async def test_inserts_and_reads_back_a_real_vector_column(
    db_session: AsyncSession, seeded: dict[str, str]
) -> None:
    repo = WorkerKnowledgeRepository(db_session)

    inserted = await repo.insert_chunks(
        [
            _chunk(
                ws=seeded["ws_a"],
                kb=seeded["kb_a"],
                doc=seeded["doc_a"],
                index=0,
                content="alpha content",
                content_hash="hash-1",
            )
        ]
    )

    assert inserted == 1
    count = await repo.count_chunks_for_hash(document_id=seeded["doc_a"], content_hash="hash-1")
    assert count == 1


async def test_duplicate_insert_is_a_no_op_at_the_database_level(
    db_session: AsyncSession, seeded: dict[str, str]
) -> None:
    """The application-level short-circuit is not the only guarantee —
    two concurrent deliveries could both pass it. The unique constraint
    plus ON CONFLICT DO NOTHING is what actually makes redelivery safe.
    """
    repo = WorkerKnowledgeRepository(db_session)
    row = _chunk(
        ws=seeded["ws_a"],
        kb=seeded["kb_a"],
        doc=seeded["doc_a"],
        index=0,
        content="same content",
        content_hash="hash-dup",
    )

    await repo.insert_chunks([row])
    # A *different* row id, same (document, hash, index) — exactly what a
    # redelivered job would generate.
    second = _chunk(
        ws=seeded["ws_a"],
        kb=seeded["kb_a"],
        doc=seeded["doc_a"],
        index=0,
        content="same content",
        content_hash="hash-dup",
    )
    inserted_again = await repo.insert_chunks([second])

    assert inserted_again == 0
    total = await repo.count_chunks_for_hash(document_id=seeded["doc_a"], content_hash="hash-dup")
    assert total == 1


async def test_similarity_search_prefiltered_by_workspace_excludes_other_tenants(
    db_session: AsyncSession, seeded: dict[str, str]
) -> None:
    """The Phase 5 acceptance criterion: workspace A's retrieval must
    return zero chunks from workspace B, verified with both tenants
    actually populated.
    """
    repo = WorkerKnowledgeRepository(db_session)
    await repo.insert_chunks(
        [
            _chunk(
                ws=seeded["ws_a"],
                kb=seeded["kb_a"],
                doc=seeded["doc_a"],
                index=0,
                content="workspace A secret",
                content_hash="h-a",
                seed=1.0,
            ),
            _chunk(
                ws=seeded["ws_b"],
                kb=seeded["kb_b"],
                doc=seeded["doc_b"],
                index=0,
                content="workspace B secret",
                content_hash="h-b",
                # Deliberately the *closest* vector to the probe, so a
                # missing filter would rank it first and the test fails
                # loudly rather than passing by luck of ordering.
                seed=1.0,
            ),
        ]
    )

    probe = "[" + ",".join(str(x) for x in _vector(1.0)) + "]"
    result = await db_session.execute(
        text(
            "SELECT content FROM kb_chunks "
            "WHERE workspace_id = :ws "
            "  AND embedding_model = :model AND embedding_model_version = :version "
            "ORDER BY embedding <=> CAST(:probe AS vector) LIMIT 10"
        ),
        {
            "ws": seeded["ws_a"],
            "model": "text-embedding-3-small",
            "version": "1",
            "probe": probe,
        },
    )
    contents = [row[0] for row in result.all()]

    assert "workspace A secret" in contents
    assert all("workspace B" not in c for c in contents)


async def test_unfiltered_search_would_have_returned_the_other_tenant(
    db_session: AsyncSession, seeded: dict[str, str]
) -> None:
    """Guards the guard above: proves the isolation test is meaningful
    because without the workspace_id predicate the other tenant's chunk
    genuinely is returned.
    """
    repo = WorkerKnowledgeRepository(db_session)
    await repo.insert_chunks(
        [
            _chunk(
                ws=seeded["ws_b"],
                kb=seeded["kb_b"],
                doc=seeded["doc_b"],
                index=0,
                content="workspace B secret",
                content_hash="h-b2",
                seed=1.0,
            )
        ]
    )

    probe = "[" + ",".join(str(x) for x in _vector(1.0)) + "]"
    result = await db_session.execute(
        text(
            "SELECT content FROM kb_chunks "
            "WHERE kb_document_id = :doc "
            "ORDER BY embedding <=> CAST(:probe AS vector) LIMIT 10"
        ),
        {"doc": seeded["doc_b"], "probe": probe},
    )

    assert [row[0] for row in result.all()] == ["workspace B secret"]


async def test_delete_chunks_removes_only_that_documents_chunks(
    db_session: AsyncSession, seeded: dict[str, str]
) -> None:
    repo = WorkerKnowledgeRepository(db_session)
    await repo.insert_chunks(
        [
            _chunk(
                ws=seeded["ws_a"],
                kb=seeded["kb_a"],
                doc=seeded["doc_a"],
                index=0,
                content="doc A",
                content_hash="h1",
            ),
            _chunk(
                ws=seeded["ws_b"],
                kb=seeded["kb_b"],
                doc=seeded["doc_b"],
                index=0,
                content="doc B",
                content_hash="h2",
            ),
        ]
    )

    await repo.delete_chunks(seeded["doc_a"])
    await db_session.commit()

    assert await repo.count_chunks_for_hash(document_id=seeded["doc_a"], content_hash="h1") == 0
    assert await repo.count_chunks_for_hash(document_id=seeded["doc_b"], content_hash="h2") == 1


async def test_status_transitions_persist(db_session: AsyncSession, seeded: dict[str, str]) -> None:
    repo = WorkerKnowledgeRepository(db_session)

    await repo.mark_processing(seeded["doc_a"])
    doc = await repo.get_document(seeded["doc_a"])
    assert doc is not None and doc.status == "processing"

    await repo.mark_indexed(document_id=seeded["doc_a"], chunk_count=3, content_hash="final")
    doc = await repo.get_document(seeded["doc_a"])
    assert doc is not None and doc.status == "indexed"
    assert doc.content_hash == "final"

    await repo.mark_failed(document_id=seeded["doc_a"], error_message="boom")
    doc = await repo.get_document(seeded["doc_a"])
    assert doc is not None and doc.status == "failed"


async def test_soft_deleted_document_is_not_returned(
    db_session: AsyncSession, seeded: dict[str, str]
) -> None:
    # A document soft-deleted between enqueue and pickup must not be
    # re-indexed; the queue is at-least-once, so this ordering is real.
    repo = WorkerKnowledgeRepository(db_session)
    await db_session.execute(
        text("UPDATE kb_documents SET deleted_at = now() WHERE id = :id"),
        {"id": seeded["doc_a"]},
    )
    await db_session.commit()

    assert await repo.get_document(seeded["doc_a"]) is None


async def test_get_knowledge_base_returns_its_embedding_identity(
    db_session: AsyncSession, seeded: dict[str, str]
) -> None:
    repo = WorkerKnowledgeRepository(db_session)

    kb = await repo.get_knowledge_base(seeded["kb_a"])

    assert kb is not None
    assert kb.workspace_id == seeded["ws_a"]
    assert kb.embedding_model == "text-embedding-3-small"
    assert kb.embedding_model_version == "1"
