from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_response_echoes_request_id(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-Id": "test-request-id"})

    assert response.headers["X-Request-Id"] == "test-request-id"


async def test_health_generates_request_id_when_absent(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.headers["X-Request-Id"]
