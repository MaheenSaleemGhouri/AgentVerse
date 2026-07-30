"""`aggregate_bucket` against a real Postgres — the rollup that closes
Phase 6 gap #5 (`docs/PHASE-6-MCP-CHECKLIST.md`: "the table and its
rollup target exist; the aggregation job does not").

Real Postgres, never mocked (CLAUDE.md §11): the whole point under test
is the `ON CONFLICT` upsert against the migration's actual
`uq_tool_metric_bucket` constraint and `percentile_cont` — both are
exactly the kind of thing a fake would let pass while broken.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from agentverse_worker.mcp.metrics_aggregation import aggregate_bucket

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
    engine = create_async_engine(_require_database_url(), pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def installed_server(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[dict[str, str]]:
    """One real workspace + installed server — `tool_metrics.installed_
    server_id` has a real FK to `installed_servers`, unlike `tool_calls`'
    own (deliberately unconstrained) column, so the upsert this test
    exercises needs a row that actually satisfies it.
    """
    now = datetime.now(UTC)
    ids = {"workspace_id": str(uuid.uuid4()), "installed_server_id": str(uuid.uuid4())}

    async with session_factory() as db:
        await db.execute(
            text("INSERT INTO workspaces (id, name, slug, created_at) VALUES (:id, :n, :s, :now)"),
            {"id": ids["workspace_id"], "n": "metrics-agg-test", "s": ids["workspace_id"][:8], "now": now},
        )
        await db.execute(
            text(
                "INSERT INTO installed_servers "
                "(id, workspace_id, mcp_server_id, display_name, transport, status, health, "
                " config, discovered_tools, created_at, updated_at) "
                "VALUES (:id, :ws, NULL, 'Test Server', 'streamable_http', 'active', 'healthy', "
                " '{}', '[]', :now, :now)"
            ),
            {"id": ids["installed_server_id"], "ws": ids["workspace_id"], "now": now},
        )
        await db.commit()

    yield ids

    async with session_factory() as db:
        await db.execute(
            text("DELETE FROM tool_metrics WHERE installed_server_id = :id"),
            {"id": ids["installed_server_id"]},
        )
        await db.execute(
            text("DELETE FROM tool_calls WHERE installed_server_id = :id"),
            {"id": ids["installed_server_id"]},
        )
        await db.execute(
            text("DELETE FROM installed_servers WHERE id = :id"),
            {"id": ids["installed_server_id"]},
        )
        await db.execute(text("DELETE FROM workspaces WHERE id = :id"), {"id": ids["workspace_id"]})
        await db.commit()


async def _insert_call(
    session: AsyncSession,
    *,
    workspace_id: str,
    installed_server_id: str,
    created_at: datetime,
    tool_name: str = "list_issues",
    status: str = "success",
    duration_ms: int = 100,
) -> None:
    await session.execute(
        text(
            "INSERT INTO tool_calls "
            "(id, created_at, workspace_id, installed_server_id, tool_name, status, "
            " arguments, duration_ms, attempt) "
            "VALUES (:id, :created_at, :ws, :server, :tool, :status, '{}', :duration, 1)"
        ),
        {
            "id": str(uuid.uuid4()),
            "created_at": created_at,
            "ws": workspace_id,
            "server": installed_server_id,
            "tool": tool_name,
            "status": status,
            "duration": duration_ms,
        },
    )


class TestAggregateBucket:
    async def test_rolls_up_calls_in_the_bucket_into_one_metrics_row(
        self, session_factory: async_sessionmaker[AsyncSession], installed_server: dict[str, str]
    ) -> None:
        bucket_start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(
            hours=2
        )

        async with session_factory() as session:
            for duration in (100, 200, 300):
                await _insert_call(
                    session,
                    workspace_id=installed_server["workspace_id"],
                    installed_server_id=installed_server["installed_server_id"],
                    created_at=bucket_start + timedelta(minutes=10),
                    duration_ms=duration,
                )
            await _insert_call(
                session,
                workspace_id=installed_server["workspace_id"],
                installed_server_id=installed_server["installed_server_id"],
                created_at=bucket_start + timedelta(minutes=20),
                status="error",
                duration_ms=50,
            )
            await session.commit()

            written = await aggregate_bucket(session, bucket_start=bucket_start)
            assert written == 1

            row = (
                (
                    await session.execute(
                        text(
                            "SELECT call_count, error_count, total_duration_ms, p95_duration_ms "
                            "FROM tool_metrics WHERE installed_server_id = :id AND bucket_start = :b"
                        ),
                        {"id": installed_server["installed_server_id"], "b": bucket_start},
                    )
                )
                .mappings()
                .one()
            )
            assert row["call_count"] == 4
            assert row["error_count"] == 1
            assert row["total_duration_ms"] == 650

    async def test_calls_outside_the_bucket_window_are_excluded(
        self, session_factory: async_sessionmaker[AsyncSession], installed_server: dict[str, str]
    ) -> None:
        bucket_start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(
            hours=3
        )

        async with session_factory() as session:
            # Inside the bucket.
            await _insert_call(
                session,
                workspace_id=installed_server["workspace_id"],
                installed_server_id=installed_server["installed_server_id"],
                created_at=bucket_start + timedelta(minutes=5),
            )
            # One second before, and exactly at the end boundary — both
            # must be excluded, proving the window is `[start, end)`.
            await _insert_call(
                session,
                workspace_id=installed_server["workspace_id"],
                installed_server_id=installed_server["installed_server_id"],
                created_at=bucket_start - timedelta(seconds=1),
            )
            await _insert_call(
                session,
                workspace_id=installed_server["workspace_id"],
                installed_server_id=installed_server["installed_server_id"],
                created_at=bucket_start + timedelta(hours=1),
            )
            await session.commit()

            await aggregate_bucket(session, bucket_start=bucket_start)

            row = (
                (
                    await session.execute(
                        text(
                            "SELECT call_count FROM tool_metrics "
                            "WHERE installed_server_id = :id AND bucket_start = :b"
                        ),
                        {"id": installed_server["installed_server_id"], "b": bucket_start},
                    )
                )
                .mappings()
                .one()
            )
            assert row["call_count"] == 1

    async def test_re_aggregating_the_same_bucket_upserts_rather_than_duplicates(
        self, session_factory: async_sessionmaker[AsyncSession], installed_server: dict[str, str]
    ) -> None:
        bucket_start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(
            hours=4
        )

        async with session_factory() as session:
            await _insert_call(
                session,
                workspace_id=installed_server["workspace_id"],
                installed_server_id=installed_server["installed_server_id"],
                created_at=bucket_start + timedelta(minutes=1),
            )
            await session.commit()
            await aggregate_bucket(session, bucket_start=bucket_start)

            # A second call lands (a straggler), then the bucket is
            # re-aggregated exactly as the periodic runner's trailing
            # window would — the row must update, not duplicate.
            await _insert_call(
                session,
                workspace_id=installed_server["workspace_id"],
                installed_server_id=installed_server["installed_server_id"],
                created_at=bucket_start + timedelta(minutes=2),
            )
            await session.commit()
            await aggregate_bucket(session, bucket_start=bucket_start)

            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT call_count FROM tool_metrics "
                            "WHERE installed_server_id = :id AND bucket_start = :b"
                        ),
                        {"id": installed_server["installed_server_id"], "b": bucket_start},
                    )
                )
                .mappings()
                .all()
            )
            assert len(rows) == 1
            assert rows[0]["call_count"] == 2

    async def test_an_hour_with_no_calls_writes_no_row(
        self, session_factory: async_sessionmaker[AsyncSession], installed_server: dict[str, str]
    ) -> None:
        bucket_start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) - timedelta(
            hours=5
        )

        async with session_factory() as session:
            written = await aggregate_bucket(session, bucket_start=bucket_start)
            assert written == 0
