"""`ToolMetricsAggregator`'s own scheduling logic — locking, the
trailing-bucket window, and shutdown. `aggregate_bucket`'s actual SQL
(the `ON CONFLICT` upsert, `percentile_cont`) is real-Postgres-only and
covered in `tests/mcp/integration/test_metrics_aggregation.py`; faking
it here would prove nothing about the one thing that could break.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

import pytest
from fakeredis.aioredis import FakeRedis

from agentverse_worker.mcp.metrics_aggregation import TRAILING_BUCKETS, ToolMetricsAggregator


class FakeAggregationRepository:
    def __init__(self) -> None:
        self.calls: list[datetime] = []

    async def run_aggregation(self, *, bucket_start: datetime) -> int:
        self.calls.append(bucket_start)
        return 1


def _aggregator(*, repo: FakeAggregationRepository, redis: FakeRedis) -> ToolMetricsAggregator:
    @asynccontextmanager
    async def repo_factory():
        yield repo

    return ToolMetricsAggregator(repo_factory=repo_factory, redis=redis, interval_seconds=60.0)


@pytest.fixture
async def fake_redis():
    redis = FakeRedis(decode_responses=True)
    yield redis
    await redis.aclose()


class TestRunOnce:
    async def test_aggregates_exactly_the_trailing_window(self, fake_redis: FakeRedis) -> None:
        repo = FakeAggregationRepository()
        aggregator = _aggregator(repo=repo, redis=fake_redis)

        total = await aggregator.run_once()

        assert total == TRAILING_BUCKETS
        assert len(repo.calls) == TRAILING_BUCKETS
        # Every call is a distinct, hour-aligned bucket — no duplicate
        # windows, no fractional-hour drift from `datetime.now()`.
        assert len(set(repo.calls)) == TRAILING_BUCKETS
        assert all(bucket.minute == 0 and bucket.second == 0 for bucket in repo.calls)

    async def test_a_second_replica_skips_the_same_window(self, fake_redis: FakeRedis) -> None:
        repo_one = FakeAggregationRepository()
        repo_two = FakeAggregationRepository()
        aggregator_one = _aggregator(repo=repo_one, redis=fake_redis)
        aggregator_two = _aggregator(repo=repo_two, redis=fake_redis)

        first_total = await aggregator_one.run_once()
        second_total = await aggregator_two.run_once()

        assert first_total == TRAILING_BUCKETS
        assert second_total == 0
        assert repo_two.calls == []


class TestRunForever:
    async def test_stop_ends_the_loop_without_waiting_out_the_full_interval(
        self, fake_redis: FakeRedis
    ) -> None:
        repo = FakeAggregationRepository()

        @asynccontextmanager
        async def repo_factory():
            yield repo

        aggregator = ToolMetricsAggregator(
            repo_factory=repo_factory, redis=fake_redis, interval_seconds=3600.0
        )

        task = asyncio.create_task(aggregator.run_forever())
        await asyncio.sleep(0.05)
        aggregator.stop()
        await asyncio.wait_for(task, timeout=2.0)
        assert task.done()
