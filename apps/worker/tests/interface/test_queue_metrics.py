from fakeredis.aioredis import FakeRedis
from httpx import AsyncClient

from agentverse_worker.infrastructure.config import get_settings
from agentverse_worker.queue.factory import build_queue


async def test_queue_metrics_reports_zero_on_empty_queue(client: AsyncClient) -> None:
    response = await client.get("/internal/queue/metrics")

    assert response.status_code == 200
    assert response.json() == {"depth": 0, "pending": 0, "dlq_depth": 0}


async def test_queue_metrics_reflects_dead_lettered_jobs(
    client: AsyncClient, fake_redis: FakeRedis
) -> None:
    # Same underlying fake_redis the `client` fixture's `get_queue`
    # override reads from — a separate queue instance is fine, since
    # depth/pending/dlq_depth are just direct queries against the
    # shared stream/group names, not per-instance state.
    setup_queue = build_queue(fake_redis, get_settings())
    await setup_queue.ensure_group()
    await setup_queue.enqueue("echo", {"force_fail": True}, max_attempts=1)
    await setup_queue.poll_once()

    response = await client.get("/internal/queue/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["dlq_depth"] == 1
    assert body["pending"] == 0
