"""Populates `tool_metrics` — closes Phase 6 gap #5
(`docs/PHASE-6-MCP-CHECKLIST.md`): the table and its rollup target have
existed since the original migration; nothing ever wrote to it.

`/runtime/metrics` (`integration_metrics_route`) still reads live from
`tool_calls` today — this job only starts populating `tool_metrics`
alongside it. Cutting the read path over to the rollup is a separate,
deliberately *not* bundled change: swapping what a metrics endpoint
reads from is exactly the kind of edit that can silently make a number
disagree with what a user already saw, and that deserves its own
dedicated verification against the live-compute path it would replace,
not a rider on this gap's fix.

Buckets are hourly and keyed by `(installed_server_id, tool_name,
bucket_start)`, matching the migration's own unique constraint — an
upsert, not an insert, so re-aggregating an hour already written
(the current, still-filling hour, or a late-arriving row from a slow
commit) corrects the row instead of duplicating it.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Protocol

from agentverse_shared.locks.distributed_lock import DistributedLock
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_worker.infrastructure.config import Settings
from agentverse_worker.infrastructure.db import get_session
from agentverse_worker.mcp.tables import tool_calls_table, tool_metrics_table

logger = logging.getLogger(__name__)

LOCK_KEY = "agentverse:worker:mcp:tool_metrics_aggregation"

#: How many trailing hourly buckets get re-aggregated each cycle. Two:
#: the hour just closed (now complete and stable) plus the hour before
#: it (self-healing — if a cycle was skipped or a call committed just
#: after the previous cycle read its window, the next cycle still
#: corrects it, rather than that bucket staying wrong forever).
TRAILING_BUCKETS = 2


def _bucket_start(moment: datetime) -> datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


async def aggregate_bucket(session: AsyncSession, *, bucket_start: datetime) -> int:
    """Rolls up one hourly bucket from `tool_calls` into `tool_metrics`.

    Returns the number of `(installed_server_id, tool_name)` rows
    written — zero and "nothing happened this hour" are the same
    outcome here, which is correct: an hour with no tool calls needs no
    metrics row, not a zeroed one.
    """
    bucket_end = bucket_start + timedelta(hours=1)
    calls = tool_calls_table

    rows = (
        (
            await session.execute(
                select(
                    calls.c.workspace_id,
                    calls.c.installed_server_id,
                    calls.c.tool_name,
                    func.count(calls.c.id).label("call_count"),
                    func.count(calls.c.id).filter(calls.c.status == "error").label("error_count"),
                    func.count(calls.c.id)
                    .filter(calls.c.status == "denied")
                    .label("denied_count"),
                    func.count(calls.c.id)
                    .filter(calls.c.status == "timeout")
                    .label("timeout_count"),
                    func.coalesce(func.sum(calls.c.duration_ms), 0).label("total_duration_ms"),
                    func.percentile_cont(0.95)
                    .within_group(calls.c.duration_ms)
                    .label("p95_duration_ms"),
                )
                .where(calls.c.created_at >= bucket_start, calls.c.created_at < bucket_end)
                .group_by(calls.c.workspace_id, calls.c.installed_server_id, calls.c.tool_name)
            )
        )
        .mappings()
        .all()
    )

    for row in rows:
        stmt = pg_insert(tool_metrics_table).values(
            id=_metric_id(row["installed_server_id"], row["tool_name"], bucket_start),
            workspace_id=row["workspace_id"],
            installed_server_id=row["installed_server_id"],
            tool_name=row["tool_name"],
            bucket_start=bucket_start,
            call_count=row["call_count"],
            error_count=row["error_count"],
            denied_count=row["denied_count"],
            timeout_count=row["timeout_count"],
            total_duration_ms=row["total_duration_ms"],
            p95_duration_ms=(
                int(row["p95_duration_ms"]) if row["p95_duration_ms"] is not None else None
            ),
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_tool_metric_bucket",
            set_={
                "call_count": stmt.excluded.call_count,
                "error_count": stmt.excluded.error_count,
                "denied_count": stmt.excluded.denied_count,
                "timeout_count": stmt.excluded.timeout_count,
                "total_duration_ms": stmt.excluded.total_duration_ms,
                "p95_duration_ms": stmt.excluded.p95_duration_ms,
            },
        )
        await session.execute(stmt)

    await session.commit()
    return len(rows)


def _metric_id(installed_server_id: str, tool_name: str, bucket_start: datetime) -> str:
    """Deterministic, not random: re-aggregating the same bucket must
    resolve to the same row via `ON CONFLICT`, and a fresh `uuid4()` on
    every insert attempt would only ever collide on the unique
    constraint columns while leaving orphaned ids nowhere in play — this
    just makes the id itself stable so an insert vs. an update is
    unambiguous even before the constraint is checked.
    """
    digest = hashlib.sha256(
        f"{installed_server_id}:{tool_name}:{bucket_start.isoformat()}".encode()
    ).digest()
    return str(uuid.UUID(bytes=digest[:16]))


class MetricsAggregationRepository(Protocol):
    async def run_aggregation(self, *, bucket_start: datetime) -> int: ...


RepoFactory = Callable[[], AbstractAsyncContextManager[MetricsAggregationRepository]]


class _SessionAggregator:
    """Adapts a raw session to `MetricsAggregationRepository` — the thin
    seam `ToolMetricsAggregator` depends on, so a test can fake it
    without a real Postgres session (CLAUDE.md §11).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def run_aggregation(self, *, bucket_start: datetime) -> int:
        return await aggregate_bucket(self._session, bucket_start=bucket_start)


class ToolMetricsAggregator:
    def __init__(
        self,
        *,
        repo_factory: RepoFactory,
        redis: Redis,
        interval_seconds: float,
    ) -> None:
        self._repo_factory = repo_factory
        self._redis = redis
        self._interval_seconds = interval_seconds
        self._stopping = asyncio.Event()

    def stop(self) -> None:
        self._stopping.set()

    async def run_forever(self) -> None:
        while not self._stopping.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("tool_metrics_aggregation_cycle_failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval_seconds)

    async def run_once(self) -> int:
        """Re-aggregates the last `TRAILING_BUCKETS` complete hours.

        Same replica-coordination pattern as `HealthSweeper.run_once` —
        one Redis lock per interval, so N worker replicas produce one
        rollup, not N races over the same upsert.
        """
        lock = DistributedLock(
            self._redis, LOCK_KEY, ttl_ms=int(self._interval_seconds * 1000)
        )
        if not await lock.acquire():
            return 0

        current_hour = _bucket_start(datetime.now(UTC))
        total = 0
        async with self._repo_factory() as repo:
            for offset in range(1, TRAILING_BUCKETS + 1):
                bucket_start = current_hour - timedelta(hours=offset)
                total += await repo.run_aggregation(bucket_start=bucket_start)
        return total


def build_tool_metrics_aggregator(redis_client: Redis, settings: Settings) -> ToolMetricsAggregator:
    @asynccontextmanager
    async def _repo_factory() -> AsyncIterator[MetricsAggregationRepository]:
        async with get_session() as session:
            yield _SessionAggregator(session)

    return ToolMetricsAggregator(
        repo_factory=_repo_factory,
        redis=redis_client,
        interval_seconds=settings.tool_metrics_aggregation_interval_seconds,
    )
