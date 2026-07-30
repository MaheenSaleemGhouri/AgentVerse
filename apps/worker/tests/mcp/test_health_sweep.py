"""`HealthSweeper` — the scheduled sweep that closes Phase 6 gap #4
(`docs/PHASE-6-MCP-CHECKLIST.md`): before this, `check_health` existed
but nothing ever called it, so `installed_servers.health` never updated
after install.

`check_health` itself (a real one-shot connect/discover/disconnect) is
monkeypatched here — these tests are about the sweep's own logic
(locking, concurrency, per-check isolation, persistence), not about
exercising a real MCP connection, which `test_mcp_factory.py`/
`test_governed_mcp.py` already cover.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from fakeredis.aioredis import FakeRedis

from agentverse_worker.mcp import health_sweep as health_sweep_module
from agentverse_worker.mcp.factory import ServerConnectionSpec
from agentverse_worker.mcp.health_sweep import HealthSweeper
from agentverse_worker.mcp.manager import HealthReport


def _spec(installed_server_id: str) -> ServerConnectionSpec:
    return ServerConnectionSpec(
        installed_server_id=installed_server_id,
        workspace_id="ws-1",
        display_name=f"Server {installed_server_id}",
        transport="streamable_http",
        endpoint_url="https://example.invalid/mcp",
    )


class FakeHealthSweepRepository:
    """Records what the sweep wrote, keyed by server id."""

    def __init__(self, specs: list[ServerConnectionSpec]) -> None:
        self._specs = specs
        self.recorded: dict[str, dict[str, object]] = {}

    async def list_active_installations(self) -> list[ServerConnectionSpec]:
        return self._specs

    async def record_health_check(
        self, *, installed_server_id: str, health: str, checked_at: datetime, error: str | None
    ) -> None:
        self.recorded[installed_server_id] = {
            "health": health,
            "checked_at": checked_at,
            "error": error,
        }


def _sweeper(
    *,
    repo: FakeHealthSweepRepository,
    redis: FakeRedis,
    concurrency: int = 5,
    check_timeout_seconds: float = 5.0,
) -> HealthSweeper:
    @asynccontextmanager
    async def repo_factory():
        yield repo

    return HealthSweeper(
        repo_factory=repo_factory,
        redis=redis,
        interval_seconds=60.0,
        concurrency=concurrency,
        check_timeout_seconds=check_timeout_seconds,
    )


@pytest.fixture
async def fake_redis():
    redis = FakeRedis(decode_responses=True)
    yield redis
    await redis.aclose()


class TestRunOnce:
    async def test_probes_every_active_installation_and_persists_the_result(
        self, fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        specs = [_spec("a"), _spec("b")]
        repo = FakeHealthSweepRepository(specs)

        async def fake_check_health(spec: ServerConnectionSpec) -> HealthReport:
            return HealthReport(
                installed_server_id=spec.installed_server_id,
                health="healthy",
                tool_count=3,
                latency_ms=42,
                error=None,
                checked_at=datetime.now(UTC),
            )

        monkeypatch.setattr(health_sweep_module, "check_health", fake_check_health)
        sweeper = _sweeper(repo=repo, redis=fake_redis)

        reports = await sweeper.run_once()

        assert {r.installed_server_id for r in reports} == {"a", "b"}
        assert repo.recorded["a"]["health"] == "healthy"
        assert repo.recorded["b"]["health"] == "healthy"

    async def test_one_server_failing_does_not_stop_the_others(
        self, fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        specs = [_spec("broken"), _spec("fine")]
        repo = FakeHealthSweepRepository(specs)

        async def fake_check_health(spec: ServerConnectionSpec) -> HealthReport:
            if spec.installed_server_id == "broken":
                raise RuntimeError("connection reset")
            return HealthReport(
                installed_server_id=spec.installed_server_id,
                health="healthy",
                tool_count=1,
                latency_ms=10,
                error=None,
                checked_at=datetime.now(UTC),
            )

        monkeypatch.setattr(health_sweep_module, "check_health", fake_check_health)
        sweeper = _sweeper(repo=repo, redis=fake_redis)

        reports = await sweeper.run_once()

        # "broken" never produced a report and never got a persisted
        # write — a crash must not fabricate a health value either.
        assert {r.installed_server_id for r in reports} == {"fine"}
        assert "broken" not in repo.recorded
        assert repo.recorded["fine"]["health"] == "healthy"

    async def test_a_hung_check_times_out_without_blocking_the_sweep(
        self, fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        specs = [_spec("hangs"), _spec("fine")]
        repo = FakeHealthSweepRepository(specs)

        async def fake_check_health(spec: ServerConnectionSpec) -> HealthReport:
            if spec.installed_server_id == "hangs":
                await asyncio.sleep(10)
            return HealthReport(
                installed_server_id=spec.installed_server_id,
                health="healthy",
                tool_count=1,
                latency_ms=5,
                error=None,
                checked_at=datetime.now(UTC),
            )

        monkeypatch.setattr(health_sweep_module, "check_health", fake_check_health)
        sweeper = _sweeper(repo=repo, redis=fake_redis, check_timeout_seconds=0.1)

        reports = await sweeper.run_once()

        assert {r.installed_server_id for r in reports} == {"fine"}
        assert "hangs" not in repo.recorded

    async def test_an_empty_catalog_produces_no_reports_and_does_not_error(
        self, fake_redis: FakeRedis
    ) -> None:
        repo = FakeHealthSweepRepository([])
        sweeper = _sweeper(repo=repo, redis=fake_redis)

        assert await sweeper.run_once() == []

    async def test_a_second_replica_skips_the_same_window(
        self, fake_redis: FakeRedis, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two `HealthSweeper`s sharing one Redis, racing for the same
        window's lock — the second must find nothing to do, which is
        what keeps N worker replicas from each hammering every MCP
        server on every interval.
        """
        specs = [_spec("a")]
        repo_one = FakeHealthSweepRepository(specs)
        repo_two = FakeHealthSweepRepository(specs)
        call_count = 0

        async def fake_check_health(spec: ServerConnectionSpec) -> HealthReport:
            nonlocal call_count
            call_count += 1
            return HealthReport(
                installed_server_id=spec.installed_server_id,
                health="healthy",
                tool_count=1,
                latency_ms=1,
                error=None,
                checked_at=datetime.now(UTC),
            )

        monkeypatch.setattr(health_sweep_module, "check_health", fake_check_health)
        sweeper_one = _sweeper(repo=repo_one, redis=fake_redis)
        sweeper_two = _sweeper(repo=repo_two, redis=fake_redis)

        first = await sweeper_one.run_once()
        second = await sweeper_two.run_once()

        assert len(first) == 1
        assert second == []
        assert call_count == 1


class TestRunForever:
    async def test_stop_ends_the_loop_without_waiting_out_the_full_interval(
        self, fake_redis: FakeRedis
    ) -> None:
        repo = FakeHealthSweepRepository([])

        @asynccontextmanager
        async def repo_factory():
            yield repo

        # A long interval — if `stop()` did not interrupt the sleep, this
        # test would itself hang for the full interval.
        sweeper = HealthSweeper(
            repo_factory=repo_factory,
            redis=fake_redis,
            interval_seconds=3600.0,
            concurrency=5,
            check_timeout_seconds=5.0,
        )

        task = asyncio.create_task(sweeper.run_forever())
        await asyncio.sleep(0.05)
        sweeper.stop()
        await asyncio.wait_for(task, timeout=2.0)
        assert task.done()
