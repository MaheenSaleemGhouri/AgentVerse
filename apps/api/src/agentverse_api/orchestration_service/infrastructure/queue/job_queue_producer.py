"""Producer side of `apps/worker`'s Redis Streams job queue (Phase 3).

This service and the worker fleet do not share code for this — no
service imports another service's internal modules (CLAUDE.md §5). The
two sides agree only on the wire contract: the stream key and this
field schema, documented in `docs/systems/queue-dlq-policy.md`. If that
schema ever changes, both sides update in lockstep against the doc,
not against each other's source.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from redis.asyncio import Redis


class JobQueueProducer:
    def __init__(self, redis: Redis, *, stream: str) -> None:
        self._redis = redis
        self._stream = stream

    async def enqueue(
        self, job_type: str, payload: dict[str, Any], *, max_attempts: int = 3
    ) -> tuple[str, str]:
        job_id = str(uuid.uuid4())
        # `xadd`'s stub is invariant over its dict value/key union, so a
        # `dict[str, Any]` literal doesn't structurally match even though
        # `str` is a union member — `dict[Any, Any]` sidesteps that at this
        # single SDK boundary rather than scattering `type: ignore`s.
        fields: dict[Any, Any] = {
            "job_id": job_id,
            "job_type": job_type,
            "payload": json.dumps(payload),
            "attempt": "0",
            "max_attempts": str(max_attempts),
        }
        stream_id = await self._redis.xadd(self._stream, fields)
        return job_id, str(stream_id)

    async def enqueue_echo_job(
        self, payload: dict[str, Any], *, max_attempts: int = 3
    ) -> tuple[str, str]:
        return await self.enqueue("echo", payload, max_attempts=max_attempts)

    async def enqueue_agent_run(self, *, run_id: str, max_attempts: int = 3) -> tuple[str, str]:
        return await self.enqueue("agent_run", {"run_id": run_id}, max_attempts=max_attempts)
