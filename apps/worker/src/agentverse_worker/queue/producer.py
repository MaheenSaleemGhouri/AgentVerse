"""Worker-side job enqueue — used only by `workflow_node_job.py` to
chain to the next DAG node's job from within the worker itself (a node
finishing is something the worker already knows synchronously, so it
enqueues the next one directly rather than round-tripping through a
second signal).

Mirrors `apps/api`'s `JobQueueProducer.enqueue` wire format exactly (job
stream key, field names) — no code is shared between the two services
for this (CLAUDE.md §5); they agree only on the wire contract, per that
module's own docstring and `docs/systems/queue-dlq-policy.md`.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from redis.asyncio import Redis


async def enqueue(
    redis: Redis, *, stream: str, job_type: str, payload: dict[str, Any], max_attempts: int = 3
) -> tuple[str, str]:
    job_id = str(uuid.uuid4())
    fields: dict[Any, Any] = {
        "job_id": job_id,
        "job_type": job_type,
        "payload": json.dumps(payload),
        "attempt": "0",
        "max_attempts": str(max_attempts),
    }
    stream_id = await redis.xadd(stream, fields)
    return job_id, str(stream_id)
