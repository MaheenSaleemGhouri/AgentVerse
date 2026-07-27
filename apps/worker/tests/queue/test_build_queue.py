"""Confirms the composition wiring in `main.build_queue` actually
registers the echo handler and produces a working queue — exercised
against a fake Redis client rather than the real ASGI lifespan
machinery (CLAUDE.md §11), which httpx's `ASGITransport` doesn't drive
by default anyway.
"""

from __future__ import annotations

from fakeredis.aioredis import FakeRedis

from agentverse_worker.infrastructure.config import Settings
from agentverse_worker.main import build_queue


async def test_build_queue_wires_echo_handler_end_to_end(fake_redis: FakeRedis) -> None:
    settings = Settings(queue_base_delay_seconds=0.01, queue_max_delay_seconds=0.02)
    queue = build_queue(fake_redis, settings)

    await queue.ensure_group()
    await queue.enqueue("echo", {"ping": "pong"})
    await queue.poll_once()

    assert await queue.pending_count() == 0
    assert await queue.dlq_depth() == 0


async def test_build_queue_dead_letters_forced_failure(fake_redis: FakeRedis) -> None:
    settings = Settings(queue_base_delay_seconds=0.01, queue_max_delay_seconds=0.02)
    queue = build_queue(fake_redis, settings)

    await queue.ensure_group()
    await queue.enqueue("echo", {"force_fail": True}, max_attempts=1)
    await queue.poll_once()

    assert await queue.dlq_depth() == 1


async def test_build_queue_registers_every_job_type(fake_redis: FakeRedis) -> None:
    """Structural check only — actually invoking the `agent_run` or
    `kb_ingest` handlers needs a live Postgres connection
    (`get_session()`), which isn't exercised here. Each handler's own
    logic is covered directly, injected with fakes, in
    `tests/agents/test_agent_run_job.py` and
    `tests/knowledge/test_kb_ingest_job.py`.

    Asserting the exact set (not just membership) is deliberate: a job
    type added to the enqueue side but never registered here would
    otherwise fail only at runtime, as an unroutable job going to the DLQ.
    """
    settings = Settings()
    queue = build_queue(fake_redis, settings)

    assert set(queue._handlers.keys()) == {"echo", "agent_run", "kb_ingest"}  # noqa: SLF001
