"""Publishes to `run:{run_id}:events` — the first real consumer of the
pub/sub channel convention reserved as scaffolding in Phase 3
(docs/systems/redis-channels.md). Live-only: nothing published here is
persisted (persisted step records go through `WorkerAgentRepository.
append_step`, a distinct write); a client that never connects, or
disconnects mid-run, loses nothing but the live view — the durable
trace is `agent_run_steps`, not this channel.
"""

from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis


def channel_name(run_id: str) -> str:
    return f"run:{run_id}:events"


async def publish_event(redis: Redis, run_id: str, event: dict[str, Any]) -> None:
    await redis.publish(channel_name(run_id), json.dumps(event))
