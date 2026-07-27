"""Publishes to `team_session:{session_id}:events`.

Deliberately a separate channel from `run:{run_id}:events` rather than a
reuse of it: a team session is not an agent run, its event vocabulary is
wider (handoffs, delegation, per-member turns), and a client subscribed
to a single agent's run should not receive team traffic it cannot
render.

Live-only, same discipline as the single-agent channel: the durable
trace is `execution_events`, and a client that disconnects mid-session
loses the live view but nothing else.
"""

from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis


def channel_name(session_id: str) -> str:
    return f"team_session:{session_id}:events"


async def publish_team_event(redis: Redis, session_id: str, event: dict[str, Any]) -> None:
    await redis.publish(channel_name(session_id), json.dumps(event))
