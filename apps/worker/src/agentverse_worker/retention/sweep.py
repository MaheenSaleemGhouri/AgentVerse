"""Enforces each workspace's configured data-retention window.

`workspace_settings.retention_days` has been storable since the settings
increment shipped, and the entity's own docstring said so plainly: it
was policy with nothing enforcing it. This sweep is the enforcement —
run history older than a workspace's window is deleted, and the deletion
is itself recorded.

What is purged, and what deliberately is not:

- **Purged:** `agent_runs` older than the cutoff. `agent_run_steps`,
  `tool_calls` and `execution_events` all cascade from it, so one delete
  removes the whole run including its trace.
- **Never purged:** `audit_logs`. It is append-only by design
  (CLAUDE.md §8) and is the record *of* retention, not subject to it.
  Purging it would erase the evidence that a purge occurred.
- **Never purged:** workspaces with `retention_days` unset — which is
  every workspace that has not opted in. No default window is invented
  here; deleting customer data because an admin never opened a settings
  page would be indefensible.

Structured like `mcp/health_sweep.py`, for the same reasons: a
long-lived task cancelled on shutdown, a Redis lock keyed to the
interval so replicas do not multiply the work, and a fresh session per
cycle rather than one held open across a whole sweep.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from agentverse_shared.locks.distributed_lock import DistributedLock
from redis.asyncio import Redis
from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_worker.infrastructure.config import Settings
from agentverse_worker.infrastructure.db import get_session
from agentverse_worker.retention.tables import (
    agent_runs_table,
    audit_logs_table,
    workspace_settings_table,
)

logger = logging.getLogger(__name__)

LOCK_KEY = "agentverse:worker:retention:sweep"

#: Below this, a "retention window" is almost certainly a typo or a unit
#: mix-up (hours entered as days), and honouring it would destroy a
#: workspace's history irreversibly. Clamped rather than rejected: the
#: admin still gets aggressive retention, just not a same-day wipe.
MIN_RETENTION_DAYS = 1


@dataclass(frozen=True, slots=True)
class PurgeResult:
    workspace_id: str
    retention_days: int
    deleted_runs: int


async def purge_workspace(
    session: AsyncSession,
    *,
    workspace_id: str,
    retention_days: int,
    batch_size: int,
    now: datetime | None = None,
) -> int:
    """Deletes one bounded batch of expired runs. Returns how many went.

    Bounded by `batch_size` so a workspace that just tightened its
    retention does not issue a single enormous DELETE holding locks on a
    hot table — the remainder is collected by later cycles.
    """
    effective_days = max(retention_days, MIN_RETENTION_DAYS)
    cutoff = (now or datetime.now(UTC)) - timedelta(days=effective_days)

    # Select-then-delete rather than a bare `DELETE ... LIMIT` (which
    # Postgres does not support) — and the subquery is `workspace_id`-
    # scoped as well as time-scoped, so a bug in the cutoff maths can
    # never reach across tenants (Rule 11).
    expiring = (
        select(agent_runs_table.c.id)
        .where(
            agent_runs_table.c.workspace_id == workspace_id,
            agent_runs_table.c.created_at < cutoff,
        )
        .limit(batch_size)
        .scalar_subquery()
    )
    # `AsyncSession.execute` is typed as returning `Result`, which has no
    # `rowcount`; a DML statement always yields a `CursorResult`, which
    # does. Cast rather than `# type: ignore`, so `.rowcount` below stays
    # type-checked instead of being waved through.
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            delete(agent_runs_table).where(agent_runs_table.c.id.in_(expiring))
        ),
    )
    deleted = result.rowcount or 0

    if deleted:
        await session.execute(
            audit_logs_table.insert().values(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                actor_user_id=None,  # system-initiated; no human actor
                action="retention.purged",
                target=None,
                outcome="success",
                metadata={
                    "deleted_runs": str(deleted),
                    "retention_days": str(effective_days),
                    "cutoff": cutoff.isoformat(),
                },
                created_at=datetime.now(UTC),
            )
        )
    await session.commit()
    return deleted


class RetentionSweepRepository:
    """The two operations a cycle needs, over one session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_workspaces_with_retention(self) -> list[tuple[str, int]]:
        result = await self._session.execute(
            select(
                workspace_settings_table.c.workspace_id,
                workspace_settings_table.c.retention_days,
            ).where(workspace_settings_table.c.retention_days.isnot(None))
        )
        return [(str(row[0]), int(row[1])) for row in result.all()]

    async def purge(self, *, workspace_id: str, retention_days: int, batch_size: int) -> int:
        return await purge_workspace(
            self._session,
            workspace_id=workspace_id,
            retention_days=retention_days,
            batch_size=batch_size,
        )


RepoFactory = Callable[[], AbstractAsyncContextManager[RetentionSweepRepository]]


class RetentionSweeper:
    def __init__(
        self,
        *,
        repo_factory: RepoFactory,
        redis: Redis,
        interval_seconds: float,
        batch_size: int,
    ) -> None:
        self._repo_factory = repo_factory
        self._redis = redis
        self._interval_seconds = interval_seconds
        self._batch_size = batch_size
        self._stopping = asyncio.Event()

    def stop(self) -> None:
        self._stopping.set()

    async def run_forever(self) -> None:
        while not self._stopping.is_set():
            try:
                await self.run_once()
            except Exception:
                # One bad cycle must not end retention enforcement
                # permanently — the next interval tries again.
                logger.exception("retention_sweep_cycle_failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval_seconds)

    async def run_once(self) -> list[PurgeResult]:
        """Runs one cycle if this replica wins the interval's lock.

        An empty result means either "another replica has this window" or
        "nothing was past its window" — both normal, neither a failure.
        """
        lock = DistributedLock(self._redis, LOCK_KEY, ttl_ms=int(self._interval_seconds * 1000))
        if not await lock.acquire():
            return []

        async with self._repo_factory() as repo:
            results: list[PurgeResult] = []
            for workspace_id, retention_days in await repo.list_workspaces_with_retention():
                deleted = await repo.purge(
                    workspace_id=workspace_id,
                    retention_days=retention_days,
                    batch_size=self._batch_size,
                )
                if deleted:
                    logger.info(
                        "retention_purged workspace_id=%s retention_days=%d deleted_runs=%d",
                        workspace_id,
                        retention_days,
                        deleted,
                    )
                    results.append(
                        PurgeResult(
                            workspace_id=workspace_id,
                            retention_days=retention_days,
                            deleted_runs=deleted,
                        )
                    )
            return results


def build_retention_sweeper(redis_client: Redis, settings: Settings) -> RetentionSweeper:
    @asynccontextmanager
    async def _repo_factory() -> AsyncIterator[RetentionSweepRepository]:
        async with get_session() as session:
            yield RetentionSweepRepository(session)

    return RetentionSweeper(
        repo_factory=_repo_factory,
        redis=redis_client,
        interval_seconds=settings.retention_sweep_interval_seconds,
        batch_size=settings.retention_sweep_batch_size,
    )
