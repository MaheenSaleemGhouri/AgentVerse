from collections.abc import AsyncIterator

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient

from agentverse_worker.infrastructure.config import get_settings
from agentverse_worker.interface.dependencies import get_queue, get_redis_client
from agentverse_worker.main import create_app
from agentverse_worker.queue.factory import build_queue


@pytest.fixture
async def fake_redis() -> AsyncIterator[FakeRedis]:
    redis = FakeRedis(decode_responses=True)
    yield redis
    await redis.aclose()


@pytest.fixture
async def client(fake_redis: FakeRedis) -> AsyncIterator[AsyncClient]:
    """Overrides the Redis-backed dependencies with a fake so route
    tests never touch the network — httpx's `ASGITransport` doesn't
    drive FastAPI's lifespan anyway, so the real `get_redis_client`/
    `get_queue` singletons are never constructed for these tests.
    """
    app = create_app()
    queue = build_queue(fake_redis, get_settings())
    await queue.ensure_group()  # mirrors what the real lifespan does before serving traffic
    app.dependency_overrides[get_redis_client] = lambda: fake_redis
    app.dependency_overrides[get_queue] = lambda: queue
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
