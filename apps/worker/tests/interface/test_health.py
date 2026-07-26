from httpx import ASGITransport, AsyncClient

from agentverse_worker.interface.dependencies import get_redis_client
from agentverse_worker.main import create_app


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_returns_ok_when_redis_reachable(client: AsyncClient) -> None:
    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_returns_503_when_redis_unreachable() -> None:
    class _BrokenRedis:
        async def ping(self) -> None:
            raise ConnectionError("simulated Redis outage")

    app = create_app()
    app.dependency_overrides[get_redis_client] = lambda: _BrokenRedis()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
