from collections.abc import AsyncIterator

import pytest
from fakeredis.aioredis import FakeRedis


@pytest.fixture
async def fake_redis() -> AsyncIterator[FakeRedis]:
    redis = FakeRedis(decode_responses=True)
    yield redis
    await redis.aclose()
