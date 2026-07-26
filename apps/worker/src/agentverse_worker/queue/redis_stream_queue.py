"""Redis Streams-backed job queue: consumer-group delivery, bounded
retry with exponential backoff, and a dead-letter queue for jobs that
exhaust their attempts (CLAUDE.md Rule 14 — background execution is
never inline, and redelivery must never double-execute silently).

Design notes (see `docs/systems/queue-dlq-policy.md` for the full
policy this implements):

- The Redis client passed in must be constructed with
  `decode_responses=True` — every field in this module is `str`, never
  `bytes`, and that's a caller-side contract rather than something this
  class re-negotiates per call.
- A crash-recovered redelivery (via `XAUTOCLAIM`, because a previous
  consumer died mid-handler without acking) is NOT the same event as an
  explicit handler failure: the former replays `job.attempt` unchanged
  when it succeeds on recovery, the latter is what actually increments
  `attempt` and drives the retry/backoff/DLQ decision. Conflating the
  two is exactly the failure mode `docs/roadmap.md` Phase 3's Risks
  section warns about.
- The backoff *delay* between retries is an in-process `asyncio.sleep`,
  not a Redis-native delayed-queue: durability holds for the retry's
  existence (it is re-published to the stream the moment the delay
  elapses), but a worker crash during that sleep window loses the
  pending retry. Documented as an accepted limitation for this phase's
  proof-of-concept scope, not silently glossed over.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
import uuid
from collections.abc import Iterable
from typing import Any

from redis.asyncio import Redis

from agentverse_worker.infrastructure.logging import job_id_var
from agentverse_worker.queue.models import Job, JobHandler, JobResult, JobStatus

logger = logging.getLogger(__name__)

StreamMessage = tuple[str, dict[str, str]]


class RedisStreamQueue:
    def __init__(
        self,
        redis: Redis,
        *,
        stream: str,
        dlq_stream: str,
        group: str,
        consumer: str,
        handlers: dict[str, JobHandler],
        visibility_timeout_ms: int = 30_000,
        base_delay_seconds: float = 0.5,
        max_delay_seconds: float = 8.0,
        block_ms: int = 5_000,
        batch_size: int = 10,
    ) -> None:
        self._redis = redis
        self._stream = stream
        self._dlq_stream = dlq_stream
        self._group = group
        self._consumer = consumer
        self._handlers = handlers
        self._visibility_timeout_ms = visibility_timeout_ms
        self._base_delay_seconds = base_delay_seconds
        self._max_delay_seconds = max_delay_seconds
        self._block_ms = block_ms
        self._batch_size = batch_size
        self._stopping = asyncio.Event()

    async def ensure_group(self) -> None:
        try:
            await self._redis.xgroup_create(self._stream, self._group, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        max_attempts: int = 3,
        job_id: str | None = None,
    ) -> str:
        job_id = job_id or str(uuid.uuid4())
        return await self._publish(job_id, job_type, payload, attempt=0, max_attempts=max_attempts)

    async def poll_once(self) -> None:
        """One iteration of the consumer loop: reclaim anything a crashed
        consumer left pending past the visibility timeout, then read and
        process a fresh batch. Any retries scheduled during this call are
        awaited before returning, so tests calling `poll_once` see a
        fully settled queue state — no fire-and-forget task left hanging.
        """
        await self._reclaim_stale()
        response = await self._redis.xreadgroup(
            self._group,
            self._consumer,
            {self._stream: ">"},
            count=self._batch_size,
            block=self._block_ms,
        )
        for _stream_name, messages in response or []:
            await self._process_batch(messages)

    async def run_forever(self) -> None:
        await self.ensure_group()
        while not self._stopping.is_set():
            await self.poll_once()

    def stop(self) -> None:
        self._stopping.set()

    async def depth(self) -> int:
        return int(await self._redis.xlen(self._stream))

    async def dlq_depth(self) -> int:
        return int(await self._redis.xlen(self._dlq_stream))

    async def pending_count(self) -> int:
        info = await self._redis.xpending(self._stream, self._group)
        return int(info["pending"]) if info else 0

    async def _reclaim_stale(self) -> None:
        try:
            _cursor, claimed, _deleted = await self._redis.xautoclaim(
                self._stream,
                self._group,
                self._consumer,
                min_idle_time=self._visibility_timeout_ms,
                start_id="0-0",
                count=self._batch_size,
            )
        except Exception:
            logger.exception("queue_reclaim_failed stream=%s", self._stream)
            return
        if claimed:
            await self._process_batch(claimed)

    async def _process_batch(self, messages: Iterable[StreamMessage]) -> None:
        tasks: list[asyncio.Task[None]] = []
        for stream_id, fields in messages:
            task = await self._handle_message(stream_id, fields)
            if task is not None:
                tasks.append(task)
        if tasks:
            await asyncio.gather(*tasks)

    async def _handle_message(
        self, stream_id: str, fields: dict[str, str]
    ) -> asyncio.Task[None] | None:
        try:
            job = self._parse(fields)
        except Exception:
            logger.exception("queue_parse_failed stream_id=%s", stream_id)
            await self._redis.xack(self._stream, self._group, stream_id)
            return None

        handler = self._handlers.get(job.job_type)
        if handler is None:
            logger.error("queue_unknown_job_type job_type=%s job_id=%s", job.job_type, job.job_id)
            await self._dead_letter(job, reason=f"unknown_job_type:{job.job_type}")
            await self._redis.xack(self._stream, self._group, stream_id)
            return None

        token = job_id_var.set(job.job_id)
        try:
            result = await handler(job)
        except Exception as exc:  # noqa: BLE001 - a handler's own bug must never crash the loop
            result = JobResult.fail(f"handler_raised:{exc!r}")
        finally:
            job_id_var.reset(token)

        await self._redis.xack(self._stream, self._group, stream_id)

        if result.status is JobStatus.SUCCEEDED:
            logger.info(
                "queue_job_succeeded job_id=%s job_type=%s attempt=%d",
                job.job_id,
                job.job_type,
                job.attempt,
            )
            return None

        if job.attempt + 1 >= job.max_attempts:
            await self._dead_letter(job, reason=result.error or "unknown_error")
            logger.error(
                "queue_job_dead_lettered job_id=%s job_type=%s attempts=%d error=%s",
                job.job_id,
                job.job_type,
                job.attempt + 1,
                result.error,
            )
            return None

        delay = min(self._base_delay_seconds * (2**job.attempt), self._max_delay_seconds)
        delay += random.uniform(0, delay * 0.25)
        logger.warning(
            "queue_job_retry_scheduled job_id=%s job_type=%s attempt=%d delay_s=%.2f",
            job.job_id,
            job.job_type,
            job.attempt + 1,
            delay,
        )
        return asyncio.create_task(self._delayed_requeue(job, delay))

    async def _delayed_requeue(self, job: Job, delay_seconds: float) -> None:
        await asyncio.sleep(delay_seconds)
        await self._publish(
            job.job_id,
            job.job_type,
            job.payload,
            attempt=job.attempt + 1,
            max_attempts=job.max_attempts,
        )

    async def _dead_letter(self, job: Job, *, reason: str) -> None:
        # `xadd`'s stub is invariant over its dict value union, so a plain
        # `dict[str, str]` literal doesn't structurally match even though
        # `str` is one of the union's members — `Any` sidesteps that at
        # this single SDK boundary rather than scattering `type: ignore`s.
        fields: dict[Any, Any] = {
            "job_id": job.job_id,
            "job_type": job.job_type,
            "payload": json.dumps(job.payload),
            "attempts_made": str(job.attempt + 1),
            "failure_reason": reason,
            "failed_at_ms": str(int(time.time() * 1000)),
        }
        await self._redis.xadd(self._dlq_stream, fields)

    async def _publish(
        self,
        job_id: str,
        job_type: str,
        payload: dict[str, Any],
        *,
        attempt: int,
        max_attempts: int,
    ) -> str:
        fields: dict[Any, Any] = {
            "job_id": job_id,
            "job_type": job_type,
            "payload": json.dumps(payload),
            "attempt": str(attempt),
            "max_attempts": str(max_attempts),
        }
        stream_id = await self._redis.xadd(self._stream, fields)
        return str(stream_id)

    def _parse(self, fields: dict[str, str]) -> Job:
        return Job(
            job_id=fields["job_id"],
            job_type=fields["job_type"],
            payload=json.loads(fields["payload"]),
            attempt=int(fields["attempt"]),
            max_attempts=int(fields["max_attempts"]),
        )
