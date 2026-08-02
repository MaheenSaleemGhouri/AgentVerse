"""`RetentionSweeper` — scheduling, locking, and per-workspace isolation.

The SQL itself (the cutoff subquery, the cascade, the audit insert) is
exercised against real Postgres in `integration/test_retention_purge.py`;
these tests pin the sweep's own behaviour with a fake repository, the
same split `test_health_sweep.py` uses.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest
from fakeredis.aioredis import FakeRedis

from agentverse_worker.retention.sweep import RetentionSweeper


class FakeRetentionRepository:
    def __init__(self, configured: dict[str, int], expired: dict[str, int]) -> None:
        self._configured = configured
        self._expired = expired
        self.purge_calls: list[tuple[str, int, int]] = []

    async def list_workspaces_with_retention(self) -> list[tuple[str, int]]:
        return list(self._configured.items())

    async def purge(self, *, workspace_id: str, retention_days: int, batch_size: int) -> int:
        self.purge_calls.append((workspace_id, retention_days, batch_size))
        available = self._expired.get(workspace_id, 0)
        deleted = min(available, batch_size)
        self._expired[workspace_id] = available - deleted
        return deleted


def _sweeper(repo: FakeRetentionRepository, *, batch_size: int = 1000) -> RetentionSweeper:
    @asynccontextmanager
    async def factory():  # type: ignore[no-untyped-def]
        yield repo

    return RetentionSweeper(
        repo_factory=factory,
        redis=FakeRedis(),
        interval_seconds=0.01,
        batch_size=batch_size,
    )


async def test_purges_only_workspaces_that_configured_retention() -> None:
    repo = FakeRetentionRepository(
        configured={"ws-with-policy": 30},
        expired={"ws-with-policy": 5, "ws-without-policy": 9999},
    )
    results = await _sweeper(repo).run_once()

    assert [r.workspace_id for r in results] == ["ws-with-policy"]
    # The unconfigured workspace is never even offered to `purge` — an
    # opt-out workspace must not depend on the purge query being correct.
    assert [call[0] for call in repo.purge_calls] == ["ws-with-policy"]
    assert repo._expired["ws-without-policy"] == 9999


async def test_a_workspace_with_nothing_expired_is_not_reported() -> None:
    repo = FakeRetentionRepository(configured={"ws-1": 7}, expired={})
    assert await _sweeper(repo).run_once() == []


async def test_deletion_is_bounded_by_the_batch_size() -> None:
    repo = FakeRetentionRepository(configured={"ws-1": 7}, expired={"ws-1": 250})
    sweeper = _sweeper(repo, batch_size=100)

    first = await sweeper.run_once()
    assert first[0].deleted_runs == 100
    # 150 remain: one cycle deliberately does not drain the backlog.
    assert repo._expired["ws-1"] == 150


async def test_only_one_replica_sweeps_a_given_window() -> None:
    redis = FakeRedis()
    repos = [
        FakeRetentionRepository(configured={"ws-1": 7}, expired={"ws-1": 10}) for _ in range(2)
    ]

    def build(repo: FakeRetentionRepository) -> RetentionSweeper:
        @asynccontextmanager
        async def factory():  # type: ignore[no-untyped-def]
            yield repo

        return RetentionSweeper(
            repo_factory=factory, redis=redis, interval_seconds=60.0, batch_size=1000
        )

    results = await asyncio.gather(*(build(repo).run_once() for repo in repos))
    assert sum(len(r) for r in results) == 1


async def test_a_failing_cycle_does_not_end_the_loop() -> None:
    class Exploding(FakeRetentionRepository):
        def __init__(self) -> None:
            super().__init__(configured={"ws-1": 7}, expired={"ws-1": 1})
            self.attempts = 0

        async def list_workspaces_with_retention(self) -> list[tuple[str, int]]:
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("transient database hiccup")
            return await super().list_workspaces_with_retention()

    repo = Exploding()
    sweeper = _sweeper(repo)
    task = asyncio.create_task(sweeper.run_forever())
    for _ in range(200):
        await asyncio.sleep(0.01)
        if repo.attempts >= 2:
            break
    sweeper.stop()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert repo.attempts >= 2
