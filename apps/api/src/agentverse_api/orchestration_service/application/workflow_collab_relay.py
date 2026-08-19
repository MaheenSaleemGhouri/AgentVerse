"""The workflow-collaboration WS relay loop, extracted from the route
binding so it is directly testable against a real Redis without needing
a real WebSocket transport (`docs/adr/0016`) — `websocket_collab_ws`'s
own route body is just: validate origin, resolve the ticket, `accept()`,
call this, translate `WebSocketDisconnect` to a clean return.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Protocol

from redis.asyncio import Redis

#: Bounded — a stray/malicious client cannot make the server buffer an
#: unbounded relayed payload (this channel carries small cursor/node-
#: position events, never document content).
DEFAULT_MAX_MESSAGE_BYTES = 8192


class WebSocketLike(Protocol):
    async def receive_text(self) -> str: ...
    async def send_text(self, data: str) -> None: ...


async def run_relay_loop(
    websocket: WebSocketLike,
    *,
    redis: Redis,
    channel: str,
    user_id: str,
    max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES,
) -> None:
    """Runs until the caller's `receive_text` raises (a disconnect) or
    is cancelled. Every inbound client message has its `user_id` field
    overwritten with the *resolved* identity before being republished —
    never trusted from the client's own payload, which would otherwise
    let any connected client broadcast presence/edits under someone
    else's name.
    """
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    async def _relay_from_redis() -> None:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            await websocket.send_text(message["data"])

    relay_task = asyncio.create_task(_relay_from_redis())
    try:
        while True:
            raw = await websocket.receive_text()
            if len(raw.encode("utf-8")) > max_message_bytes:
                continue
            try:
                event = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if not isinstance(event, dict):
                continue
            event["user_id"] = user_id
            await redis.publish(channel, json.dumps(event))
    finally:
        relay_task.cancel()
        with contextlib.suppress(Exception):
            await relay_task
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()  # type: ignore[no-untyped-call]
