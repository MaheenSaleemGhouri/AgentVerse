"""The producer's contract with apps/worker's consumer is the wire
schema, not shared code — this test asserts the fields this side
writes are exactly what `RedisStreamQueue._parse` on the worker side
expects (job_id, job_type, payload as JSON, attempt, max_attempts).
"""

from __future__ import annotations

import json

from fakeredis.aioredis import FakeRedis

from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)

STREAM = "queue:jobs"


async def test_enqueue_echo_job_writes_expected_field_schema(fake_redis: FakeRedis) -> None:
    producer = JobQueueProducer(fake_redis, stream=STREAM)

    job_id, stream_id = await producer.enqueue_echo_job({"hello": "world"}, max_attempts=5)

    entries = await fake_redis.xrange(STREAM)
    assert len(entries) == 1
    entry_id, fields = entries[0]
    assert entry_id == stream_id
    assert fields["job_id"] == job_id
    assert fields["job_type"] == "echo"
    assert json.loads(fields["payload"]) == {"hello": "world"}
    assert fields["attempt"] == "0"
    assert fields["max_attempts"] == "5"


async def test_enqueue_echo_job_defaults_max_attempts_to_three(fake_redis: FakeRedis) -> None:
    producer = JobQueueProducer(fake_redis, stream=STREAM)

    await producer.enqueue_echo_job({})

    _entry_id, fields = (await fake_redis.xrange(STREAM))[0]
    assert fields["max_attempts"] == "3"
