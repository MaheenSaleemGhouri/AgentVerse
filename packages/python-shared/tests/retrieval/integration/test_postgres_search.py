"""`PostgresChunkSearch` against real Postgres + pgvector.

The tenant-isolation criterion in docs/roadmap.md Phase 5 is a claim
about SQL, and SQL is the one thing a fake repository cannot check.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_shared.retrieval.postgres_search import PostgresChunkSearch
from tests.retrieval.integration.conftest import (
    MODEL,
    VERSION,
    insert_chunk,
    vector_literal,
)

pytestmark = pytest.mark.integration


async def _search(
    session: AsyncSession, seeded: dict[str, str], *, seed: float = 1.0, limit: int = 10
) -> list[str]:
    hits = await PostgresChunkSearch(session).vector_search(
        workspace_id=seeded["ws_a"],
        knowledge_base_ids=[seeded["kb_a"]],
        embedding=vector_literal(seed),
        embedding_model=MODEL,
        embedding_model_version=VERSION,
        limit=limit,
    )
    return [h.content for h in hits]


async def test_vector_search_returns_nearest_first_with_a_similarity_score(
    db_session: AsyncSession, seeded: dict[str, str]
) -> None:
    await insert_chunk(
        db_session,
        workspace_id=seeded["ws_a"],
        kb_id=seeded["kb_a"],
        document_id=seeded["doc_a"],
        content="near match",
        embedding=vector_literal(1.0),
    )
    await insert_chunk(
        db_session,
        workspace_id=seeded["ws_a"],
        kb_id=seeded["kb_a"],
        document_id=seeded["doc_a"],
        content="far match",
        embedding=vector_literal(-1.0),
        index=1,
    )

    hits = await PostgresChunkSearch(db_session).vector_search(
        workspace_id=seeded["ws_a"],
        knowledge_base_ids=[seeded["kb_a"]],
        embedding=vector_literal(1.0),
        embedding_model=MODEL,
        embedding_model_version=VERSION,
        limit=10,
    )

    assert [h.content for h in hits] == ["near match", "far match"]
    # Score is a similarity (higher is better), not the raw distance.
    assert hits[0].score > hits[1].score


async def test_vector_search_excludes_another_workspace(
    db_session: AsyncSession, seeded: dict[str, str]
) -> None:
    """The Phase 5 acceptance criterion. Workspace B's chunk is given the
    *identical* vector to the probe, so a missing filter would rank it
    first and this test would fail loudly rather than pass by luck.
    """
    await insert_chunk(
        db_session,
        workspace_id=seeded["ws_a"],
        kb_id=seeded["kb_a"],
        document_id=seeded["doc_a"],
        content="workspace A secret",
        embedding=vector_literal(0.5),
    )
    await insert_chunk(
        db_session,
        workspace_id=seeded["ws_b"],
        kb_id=seeded["kb_b"],
        document_id=seeded["doc_b"],
        content="workspace B secret",
        embedding=vector_literal(1.0),
    )

    contents = await _search(db_session, seeded)

    assert contents == ["workspace A secret"]


async def test_unfiltered_query_would_have_returned_the_other_tenant(
    db_session: AsyncSession, seeded: dict[str, str]
) -> None:
    """Guards the guard above: without the predicate the other tenant's
    chunk genuinely is the top hit, so the isolation test is meaningful.
    """
    await insert_chunk(
        db_session,
        workspace_id=seeded["ws_b"],
        kb_id=seeded["kb_b"],
        document_id=seeded["doc_b"],
        content="workspace B secret",
        embedding=vector_literal(1.0),
    )

    result = await db_session.execute(
        text(
            "SELECT content FROM kb_chunks WHERE knowledge_base_id = :kb "
            "ORDER BY embedding <=> CAST(:probe AS vector) LIMIT 5"
        ),
        {
            "kb": seeded["kb_b"],
            "probe": "[" + ",".join(repr(float(x)) for x in vector_literal(1.0)) + "]",
        },
    )
    assert [row[0] for row in result.all()] == ["workspace B secret"]


async def test_vector_search_excludes_a_different_embedding_model_version(
    db_session: AsyncSession, seeded: dict[str, str]
) -> None:
    """A knowledge base mid-backfill holds chunks under two versions.
    Comparing across them returns meaningless scores with no error, so the
    filter is the only thing preventing silent quality collapse.
    """
    await insert_chunk(
        db_session,
        workspace_id=seeded["ws_a"],
        kb_id=seeded["kb_a"],
        document_id=seeded["doc_a"],
        content="current version",
        embedding=vector_literal(0.5),
    )
    await insert_chunk(
        db_session,
        workspace_id=seeded["ws_a"],
        kb_id=seeded["kb_a"],
        document_id=seeded["doc_a"],
        content="stale version",
        embedding=vector_literal(1.0),
        index=1,
        version="0",
    )

    assert await _search(db_session, seeded) == ["current version"]


async def test_vector_search_excludes_a_knowledge_base_not_asked_for(
    db_session: AsyncSession, seeded: dict[str, str]
) -> None:
    # Same workspace, different KB — an agent attached to KB A must not
    # retrieve from a KB it was never given.
    await insert_chunk(
        db_session,
        workspace_id=seeded["ws_a"],
        kb_id=seeded["kb_a"],
        document_id=seeded["doc_a"],
        content="asked for",
        embedding=vector_literal(0.5),
    )

    hits = await PostgresChunkSearch(db_session).vector_search(
        workspace_id=seeded["ws_a"],
        knowledge_base_ids=[seeded["kb_b"]],
        embedding=vector_literal(0.5),
        embedding_model=MODEL,
        embedding_model_version=VERSION,
        limit=10,
    )
    assert hits == []


async def test_vector_search_honours_the_limit(
    db_session: AsyncSession, seeded: dict[str, str]
) -> None:
    for i in range(5):
        await insert_chunk(
            db_session,
            workspace_id=seeded["ws_a"],
            kb_id=seeded["kb_a"],
            document_id=seeded["doc_a"],
            content=f"chunk {i}",
            embedding=vector_literal(1.0 - i * 0.1),
            index=i,
        )

    assert len(await _search(db_session, seeded, limit=2)) == 2


async def test_keyword_search_matches_terms_and_ranks_them(
    db_session: AsyncSession, seeded: dict[str, str]
) -> None:
    await insert_chunk(
        db_session,
        workspace_id=seeded["ws_a"],
        kb_id=seeded["kb_a"],
        document_id=seeded["doc_a"],
        content="cancel your subscription from billing settings",
        embedding=vector_literal(0.1),
    )
    await insert_chunk(
        db_session,
        workspace_id=seeded["ws_a"],
        kb_id=seeded["kb_a"],
        document_id=seeded["doc_a"],
        content="entirely unrelated onboarding text",
        embedding=vector_literal(0.2),
        index=1,
    )

    hits = await PostgresChunkSearch(db_session).keyword_search(
        workspace_id=seeded["ws_a"],
        knowledge_base_ids=[seeded["kb_a"]],
        query="cancel subscription",
        embedding_model=MODEL,
        embedding_model_version=VERSION,
        limit=10,
    )

    assert [h.content for h in hits] == ["cancel your subscription from billing settings"]


async def test_keyword_search_excludes_another_workspace(
    db_session: AsyncSession, seeded: dict[str, str]
) -> None:
    await insert_chunk(
        db_session,
        workspace_id=seeded["ws_b"],
        kb_id=seeded["kb_b"],
        document_id=seeded["doc_b"],
        content="cancel subscription workspace B",
        embedding=vector_literal(1.0),
    )

    hits = await PostgresChunkSearch(db_session).keyword_search(
        workspace_id=seeded["ws_a"],
        knowledge_base_ids=[seeded["kb_a"]],
        query="cancel subscription",
        embedding_model=MODEL,
        embedding_model_version=VERSION,
        limit=10,
    )
    assert hits == []


async def test_keyword_search_treats_tsquery_operators_as_literal_text(
    db_session: AsyncSession, seeded: dict[str, str]
) -> None:
    """`plainto_tsquery` must neutralize operator syntax — a user query is
    untrusted input reaching a query language (CLAUDE.md §10).
    """
    await insert_chunk(
        db_session,
        workspace_id=seeded["ws_a"],
        kb_id=seeded["kb_a"],
        document_id=seeded["doc_a"],
        content="billing documentation",
        embedding=vector_literal(0.1),
    )

    search = PostgresChunkSearch(db_session)
    common = {
        "workspace_id": seeded["ws_a"],
        "knowledge_base_ids": [seeded["kb_a"]],
        "embedding_model": MODEL,
        "embedding_model_version": VERSION,
        "limit": 10,
    }

    # Operator characters are stripped rather than parsed: no syntax
    # error, and the surviving lexemes are simply ANDed.
    plain = await search.keyword_search(query="billing & documentation", **common)  # type: ignore[arg-type]
    assert [h.content for h in plain] == ["billing documentation"]

    # A negation the user typed does not take effect — were `!` honoured
    # as a tsquery operator, this row would be excluded.
    negated = await search.keyword_search(query="billing !documentation", **common)  # type: ignore[arg-type]
    assert [h.content for h in negated] == ["billing documentation"]


async def test_both_arms_draw_from_the_same_candidate_pool(
    db_session: AsyncSession, seeded: dict[str, str]
) -> None:
    """Fusion is only meaningful if a chunk the vector arm structurally
    cannot return also cannot enter through the keyword arm.
    """
    await insert_chunk(
        db_session,
        workspace_id=seeded["ws_a"],
        kb_id=seeded["kb_a"],
        document_id=seeded["doc_a"],
        content="stale version billing text",
        embedding=vector_literal(1.0),
        version="0",
    )

    search = PostgresChunkSearch(db_session)
    common = {
        "workspace_id": seeded["ws_a"],
        "knowledge_base_ids": [seeded["kb_a"]],
        "embedding_model": MODEL,
        "embedding_model_version": VERSION,
        "limit": 10,
    }

    assert await search.vector_search(embedding=vector_literal(1.0), **common) == []  # type: ignore[arg-type]
    assert await search.keyword_search(query="billing text", **common) == []  # type: ignore[arg-type]
