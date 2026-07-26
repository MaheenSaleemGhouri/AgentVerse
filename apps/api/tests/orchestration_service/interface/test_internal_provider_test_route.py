"""Route-level test: the internal test route wires request -> service ->
adapter correctly, with a `FakeProviderAdapter` standing in for OpenAI
(CLAUDE.md §11 — no network I/O in a unit test)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from agentverse_api.auth_service.interface.dependencies.internal_service_auth import (
    require_internal_service,
)
from agentverse_api.main import create_app
from agentverse_api.orchestration_service.application.provider_test_service import (
    ProviderTestService,
)
from agentverse_api.orchestration_service.domain.entities import (
    ChatMessage,
    StreamDelta,
    StreamDone,
    TokenUsage,
)
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_provider_test_service,
)
from tests.fakes.provider_adapter import FakeProviderAdapter


@pytest.fixture
async def client_with_fake_provider() -> AsyncIterator[tuple[AsyncClient, FakeProviderAdapter]]:
    fake_adapter = FakeProviderAdapter(
        stream_events=[
            StreamDelta(text="Hel"),
            StreamDelta(text="lo"),
            StreamDone(
                finish_reason="stop",
                usage=TokenUsage(prompt_tokens=4, completion_tokens=2),
            ),
        ]
    )
    app = create_app()
    app.dependency_overrides[require_internal_service] = lambda: None
    app.dependency_overrides[get_provider_test_service] = lambda: ProviderTestService(
        adapter=fake_adapter
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, fake_adapter


@pytest.mark.asyncio
async def test_stream_route_returns_sse_frames(
    client_with_fake_provider: tuple[AsyncClient, FakeProviderAdapter],
) -> None:
    client, fake_adapter = client_with_fake_provider

    response = await client.post("/internal/provider-test/stream", json={"prompt": "hello there"})

    assert response.status_code == 200
    frames = [
        json.loads(line[len("data: ") :])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert frames[0] == {"type": "delta", "text": "Hel"}
    assert frames[1] == {"type": "delta", "text": "lo"}
    assert frames[2]["type"] == "done"
    assert frames[2]["prompt_tokens"] == 4
    assert frames[2]["completion_tokens"] == 2

    assert len(fake_adapter.requests) == 1
    assert fake_adapter.requests[0].messages == [ChatMessage(role="user", content="hello there")]


@pytest.mark.asyncio
async def test_stream_route_rejects_empty_prompt(
    client_with_fake_provider: tuple[AsyncClient, FakeProviderAdapter],
) -> None:
    client, _ = client_with_fake_provider
    response = await client.post("/internal/provider-test/stream", json={"prompt": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_stream_route_rejects_oversized_prompt(
    client_with_fake_provider: tuple[AsyncClient, FakeProviderAdapter],
) -> None:
    client, _ = client_with_fake_provider
    response = await client.post("/internal/provider-test/stream", json={"prompt": "x" * 4001})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_stream_route_requires_internal_secret_when_not_overridden() -> None:
    """Zero trust (CLAUDE.md §10): without the shared-secret dependency
    overridden, an unauthenticated internal call is rejected — the
    network boundary alone is never sufficient authorization."""
    app = create_app()
    app.dependency_overrides[get_provider_test_service] = lambda: ProviderTestService(
        adapter=FakeProviderAdapter()
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/internal/provider-test/stream", json={"prompt": "hi"})
    assert response.status_code == 401
