from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient

from agentverse_api.auth_service.interface.dependencies.internal_service_auth import (
    require_internal_service,
)
from agentverse_api.main import create_app
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_job_queue_producer,
)

STREAM = "queue:jobs"


@pytest.fixture
async def client_with_fake_queue(
    fake_redis: FakeRedis,
) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[require_internal_service] = lambda: None
    app.dependency_overrides[get_job_queue_producer] = lambda: JobQueueProducer(
        fake_redis, stream=STREAM
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_enqueue_route_writes_job_to_stream(
    client_with_fake_queue: AsyncClient, fake_redis: FakeRedis
) -> None:
    response = await client_with_fake_queue.post(
        "/internal/job-test/enqueue", json={"payload": {"n": 1}, "max_attempts": 2}
    )

    assert response.status_code == 200
    body = response.json()
    assert "job_id" in body and "stream_id" in body

    entries = await fake_redis.xrange(STREAM)
    assert len(entries) == 1
    assert entries[0][1]["max_attempts"] == "2"


async def test_enqueue_route_folds_force_fail_into_payload(
    client_with_fake_queue: AsyncClient, fake_redis: FakeRedis
) -> None:
    response = await client_with_fake_queue.post(
        "/internal/job-test/enqueue", json={"force_fail": True}
    )

    assert response.status_code == 200
    _entry_id, fields = (await fake_redis.xrange(STREAM))[0]
    assert json.loads(fields["payload"])["force_fail"] is True


async def test_enqueue_route_requires_internal_secret_when_not_overridden() -> None:
    """Zero trust (CLAUDE.md §10): without the shared-secret dependency
    overridden, an unauthenticated internal call is rejected."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/internal/job-test/enqueue", json={})
    assert response.status_code == 401
