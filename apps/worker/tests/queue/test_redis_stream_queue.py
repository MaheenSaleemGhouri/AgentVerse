"""Exercises the four behaviors docs/roadmap.md Phase 3 names as
acceptance criteria: exactly-once ack on success, bounded retry with
backoff, dead-lettering after exhausting attempts, and (implicitly)
that a crash-recovered redelivery is distinct from an explicit retry.
Uses fakeredis so this is a fast unit test, not an integration test —
CLAUDE.md §11.
"""

from __future__ import annotations

from fakeredis.aioredis import FakeRedis

from agentverse_worker.queue.models import Job, JobResult
from agentverse_worker.queue.redis_stream_queue import RedisStreamQueue

STREAM = "queue:jobs"
DLQ = "queue:jobs.dlq"
GROUP = "workers"


def make_queue(fake_redis: FakeRedis, handlers, **overrides) -> RedisStreamQueue:
    return RedisStreamQueue(
        fake_redis,
        stream=STREAM,
        dlq_stream=DLQ,
        group=GROUP,
        consumer=overrides.pop("consumer", "worker-1"),
        handlers=handlers,
        base_delay_seconds=0.01,
        max_delay_seconds=0.02,
        block_ms=100,
        **overrides,
    )


async def test_successful_job_is_acked_exactly_once(fake_redis: FakeRedis) -> None:
    calls: list[Job] = []

    async def handler(job: Job) -> JobResult:
        calls.append(job)
        return JobResult.ok({"echo": job.payload})

    queue = make_queue(fake_redis, {"echo": handler})
    await queue.ensure_group()
    await queue.enqueue("echo", {"hello": "world"})

    await queue.poll_once()

    assert len(calls) == 1
    assert calls[0].payload == {"hello": "world"}
    assert await queue.pending_count() == 0
    assert await queue.dlq_depth() == 0


async def test_job_retries_with_backoff_then_succeeds(fake_redis: FakeRedis) -> None:
    attempts: list[int] = []

    async def flaky_handler(job: Job) -> JobResult:
        attempts.append(job.attempt)
        if job.attempt == 0:
            return JobResult.fail("transient error")
        return JobResult.ok()

    queue = make_queue(fake_redis, {"echo": flaky_handler})
    await queue.ensure_group()
    await queue.enqueue("echo", {}, max_attempts=3)

    await queue.poll_once()  # attempt 0 fails, retry is scheduled and republished
    await queue.poll_once()  # attempt 1 is read and succeeds

    assert attempts == [0, 1]
    assert await queue.dlq_depth() == 0
    assert await queue.pending_count() == 0


async def test_job_is_dead_lettered_after_exhausting_retries(fake_redis: FakeRedis) -> None:
    attempts: list[int] = []

    async def always_fails(job: Job) -> JobResult:
        attempts.append(job.attempt)
        return JobResult.fail("permanent error")

    queue = make_queue(fake_redis, {"echo": always_fails})
    await queue.ensure_group()
    await queue.enqueue("echo", {"x": 1}, max_attempts=2)

    await queue.poll_once()  # attempt 0 fails -> retry scheduled (attempt 1 < max_attempts 2)
    await queue.poll_once()  # attempt 1 fails -> exhausted -> dead-lettered

    assert attempts == [0, 1]
    assert await queue.dlq_depth() == 1
    assert await queue.pending_count() == 0

    dlq_entries = await fake_redis.xrange(DLQ)
    assert len(dlq_entries) == 1
    _dlq_id, fields = dlq_entries[0]
    assert fields["failure_reason"] == "permanent error"
    assert fields["attempts_made"] == "2"


async def test_unknown_job_type_is_dead_lettered_without_retry(fake_redis: FakeRedis) -> None:
    queue = make_queue(fake_redis, handlers={})
    await queue.ensure_group()
    await queue.enqueue("mystery_type", {})

    await queue.poll_once()

    assert await queue.dlq_depth() == 1
    assert await queue.pending_count() == 0
    _dlq_id, fields = (await fake_redis.xrange(DLQ))[0]
    assert fields["failure_reason"].startswith("unknown_job_type:")


async def test_crashed_consumers_message_is_reclaimed_and_processed_once(
    fake_redis: FakeRedis,
) -> None:
    """Simulates worker-a reading a message and crashing before acking it.
    worker-b (a second consumer in the same group) must reclaim and
    process it — and because this is crash recovery, not an explicit
    handler failure, `attempt` must stay at 0, not be incremented.
    """
    setup_queue = make_queue(fake_redis, handlers={}, consumer="worker-a")
    await setup_queue.ensure_group()
    await setup_queue.enqueue("echo", {"n": 1})

    # worker-a reads it (claims delivery) and then "crashes" — never acks.
    await fake_redis.xreadgroup(GROUP, "worker-a", {STREAM: ">"}, count=1)
    assert await setup_queue.pending_count() == 1

    seen_attempts: list[int] = []

    async def handler(job: Job) -> JobResult:
        seen_attempts.append(job.attempt)
        return JobResult.ok()

    recovering_queue = make_queue(
        fake_redis, {"echo": handler}, consumer="worker-b", visibility_timeout_ms=0
    )
    await recovering_queue.poll_once()

    assert seen_attempts == [0]
    assert await recovering_queue.pending_count() == 0
