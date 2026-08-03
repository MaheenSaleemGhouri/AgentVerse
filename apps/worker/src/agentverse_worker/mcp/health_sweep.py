"""Scheduled MCP health monitoring — closes a Phase 6 gap that turned
out larger than documented.

`manager.check_health()` has existed since the original migration, but
nothing in the codebase ever called it: no route, no job, no schedule.
`installed_servers.health`/`last_health_check_at` were write-once at
install time and never updated again — a server that died between runs
kept showing whatever health it had the day it was connected
(`docs/PHASE-6-MCP-CHECKLIST.md` gap #4, understated as "on-demand, not
scheduled" when the on-demand path did not exist either).

`HealthSweeper` is this service's second background task, run the same
way the queue consumer is (`main.py`'s lifespan): a long-lived
`run_forever()` cancelled on shutdown. A Redis lock keyed to the sweep
interval keeps only one worker replica performing the sweep in any
given window — every replica loops on the same interval, but only the
one that wins `acquire()` for that window actually probes servers, so
scaling worker replicas does not multiply load against third-party
MCP endpoints.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime
from typing import Protocol

from agentverse_shared.locks.distributed_lock import DistributedLock
from agentverse_shared.security.envelope import CredentialVault, KeyRing
from redis.asyncio import Redis

from agentverse_worker.infrastructure.config import Settings
from agentverse_worker.infrastructure.db import get_session
from agentverse_worker.mcp.factory import ServerConnectionSpec
from agentverse_worker.mcp.manager import HealthReport, check_health
from agentverse_worker.mcp.repository import WorkerIntegrationRepository

logger = logging.getLogger(__name__)

#: One lock, platform-wide — the sweep is a single logical job, not one
#: per server, so there is exactly one thing to coordinate replicas on.
LOCK_KEY = "agentverse:worker:mcp:health_sweep"


class HealthSweepRepository(Protocol):
    """What the sweep needs, narrowly — mirrors
    `IntegrationRepositoryProtocol`'s own reasoning: a fake satisfying
    this two-method surface tests the sweep without Postgres or a real
    MCP server (CLAUDE.md §11).
    """

    async def list_active_installations(self) -> list[ServerConnectionSpec]: ...

    async def record_health_check(
        self, *, installed_server_id: str, health: str, checked_at: datetime, error: str | None
    ) -> None: ...


RepoFactory = Callable[[], AbstractAsyncContextManager[HealthSweepRepository]]


class HealthSweeper:
    def __init__(
        self,
        *,
        repo_factory: RepoFactory,
        redis: Redis,
        interval_seconds: float,
        concurrency: int,
        check_timeout_seconds: float,
    ) -> None:
        """`repo_factory` is a zero-arg async context manager factory
        (`lambda: get_session()`-shaped, opening a fresh repository per
        cycle) rather than one shared repository — a sweep can span
        many minutes across many servers, and holding one DB session
        for that whole duration would starve the connection pool the
        same way an LLM call inside a transaction would (CLAUDE.md §7).
        """
        self._repo_factory = repo_factory
        self._redis = redis
        self._interval_seconds = interval_seconds
        self._concurrency = concurrency
        self._check_timeout_seconds = check_timeout_seconds
        self._stopping = asyncio.Event()

    def stop(self) -> None:
        self._stopping.set()

    async def run_forever(self) -> None:
        while not self._stopping.is_set():
            try:
                await self.run_once()
            except Exception:
                # One bad cycle (a DB hiccup, a Redis blip) must not end
                # the sweep permanently — the next interval tries again.
                logger.exception("mcp_health_sweep_cycle_failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopping.wait(), timeout=self._interval_seconds)

    async def run_once(self) -> list[HealthReport]:
        """Runs one sweep cycle if this replica wins the interval's lock.

        Returns the reports actually produced — an empty list both when
        another replica already won this window and when there is
        nothing installed to check, which is why callers (and tests)
        should not read "empty" as "the sweep is broken."
        """
        lock = DistributedLock(self._redis, LOCK_KEY, ttl_ms=int(self._interval_seconds * 1000))
        if not await lock.acquire():
            return []

        async with self._repo_factory() as repo:
            specs = await repo.list_active_installations()
            semaphore = asyncio.Semaphore(self._concurrency)

            async def _probe(spec: ServerConnectionSpec) -> HealthReport | None:
                async with semaphore:
                    try:
                        report = await asyncio.wait_for(
                            check_health(spec), timeout=self._check_timeout_seconds
                        )
                    except TimeoutError:
                        logger.warning(
                            "mcp_health_check_timed_out installed_server_id=%s",
                            spec.installed_server_id,
                        )
                        return None
                    except Exception:
                        # A crashing check must cost that one server, not
                        # the rest of the sweep — logged, not re-raised.
                        logger.exception(
                            "mcp_health_check_failed installed_server_id=%s",
                            spec.installed_server_id,
                        )
                        return None
                    await repo.record_health_check(
                        installed_server_id=report.installed_server_id,
                        health=report.health,
                        checked_at=report.checked_at,
                        error=report.error,
                    )
                    return report

            results = await asyncio.gather(*(_probe(spec) for spec in specs))
            return [report for report in results if report is not None]


def build_health_sweeper(redis_client: Redis, settings: Settings) -> HealthSweeper:
    """Composition wiring, same rationale as `queue/factory.py`'s
    `build_queue`: callable directly in tests with a fake Redis client
    and custom `Settings` (tiny interval, tiny timeout) — CLAUDE.md §11.
    """
    # Built once, like `build_queue`'s vault: read from the environment
    # at construction so a missing key fails at startup, not on the
    # first sweep cycle three minutes after boot.
    vault = CredentialVault(KeyRing.from_env())

    @asynccontextmanager
    async def _repo_factory() -> AsyncIterator[HealthSweepRepository]:
        async with get_session() as session:
            yield WorkerIntegrationRepository(session, vault)

    return HealthSweeper(
        repo_factory=_repo_factory,
        redis=redis_client,
        interval_seconds=settings.mcp_health_sweep_interval_seconds,
        concurrency=settings.mcp_health_sweep_concurrency,
        check_timeout_seconds=settings.mcp_health_sweep_check_timeout_seconds,
    )
