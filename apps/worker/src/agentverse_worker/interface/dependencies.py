"""Shared interface-layer dependencies — injectable so routes stay
testable against a fake Redis client/queue without needing FastAPI's
ASGI lifespan to actually run (CLAUDE.md §11; httpx's `ASGITransport`
doesn't drive lifespan events, so `main.lifespan`'s own construction
isn't reachable from a plain route test).
"""

from __future__ import annotations

from functools import lru_cache

from redis.asyncio import Redis
from redis.asyncio import from_url as redis_from_url

from agentverse_worker.infrastructure.config import get_settings
from agentverse_worker.queue.factory import build_queue
from agentverse_worker.queue.redis_stream_queue import RedisStreamQueue


@lru_cache
def get_redis_client() -> Redis:
    """Process-wide singleton — shared by the queue consumer loop and
    the `/ready` connectivity check, so there is exactly one connection
    pool per process, not one per consumer.
    """
    settings = get_settings()
    return redis_from_url(  # type: ignore[no-untyped-call,no-any-return]  # redis-py's own stub is untyped here
        settings.redis_url, decode_responses=True
    )


@lru_cache
def get_queue() -> RedisStreamQueue:
    """Process-wide singleton — the same queue instance the consumer
    loop runs and the metrics route reports on.
    """
    return build_queue(get_redis_client(), get_settings())
