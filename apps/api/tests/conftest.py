from collections.abc import AsyncIterator

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient

from agentverse_api.main import create_app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def fake_redis() -> AsyncIterator[FakeRedis]:
    redis = FakeRedis(decode_responses=True)
    yield redis
    await redis.aclose()
