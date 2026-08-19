"""Workflow-canvas collaboration WebSocket against real Postgres +
Redis — the ticket mint/burn handshake (over a real WS transport) and
the pub/sub relay loop (via `run_relay_loop` directly, against a fake
`WebSocketLike` — see its module docstring for why: `TestClient.
websocket_connect` inside an `async def` pytest-asyncio test is a known
ecosystem incompatibility, not a defect in the route) are both
guarantees a fake redis cannot prove (docs/adr/0016).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.infrastructure.models import User
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
    get_current_identity_optional,
)
from agentverse_api.infrastructure.db import get_db_session
from agentverse_api.main import create_app
from agentverse_api.orchestration_service.application.workflow_collab_relay import run_relay_loop
from agentverse_api.orchestration_service.interface.dependencies.services import get_redis_client

pytestmark = pytest.mark.integration


class _FakeWebSocket:
    """A `WebSocketLike` fake backed by asyncio queues, so the relay
    loop can be driven entirely inside the test's own event loop —
    zero `TestClient`/real-WS-transport involvement.
    """

    def __init__(self) -> None:
        self._inbound: asyncio.Queue[str] = asyncio.Queue()
        self.sent: list[str] = []

    def push(self, data: str) -> None:
        self._inbound.put_nowait(data)

    async def receive_text(self) -> str:
        return await self._inbound.get()

    async def send_text(self, data: str) -> None:
        self.sent.append(data)


async def _make_user(session: AsyncSession, user_id: str) -> None:
    session.add(
        User(
            id=user_id, name=user_id, email=f"{user_id}@example.com", email_verified=False,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
    )
    await session.commit()


@pytest.fixture
async def harness(
    db_session: AsyncSession,
) -> AsyncIterator[dict[str, object]]:
    app = create_app()

    async def db_session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    # A *factory*, not a shared instance: each `TestClient.websocket_
    # connect` runs the ASGI app in its own thread with its own event
    # loop (starlette's blocking portal), and an asyncio-native Redis
    # client is bound to whichever loop first used it — sharing one
    # instance across connections crosses loops and breaks the
    # underlying StreamReader. The mint-ticket REST calls (via
    # `AsyncClient`/`ASGITransport`, same loop as the test itself) are
    # unaffected either way.
    def _fresh_redis() -> Redis:
        return Redis.from_url(  # type: ignore[no-any-return]
            "redis://localhost:6379/0", decode_responses=True
        )

    app.dependency_overrides[get_db_session] = db_session_override
    app.dependency_overrides[get_redis_client] = _fresh_redis

    def make_rest_client(user_id: str) -> AsyncClient:
        app.dependency_overrides[get_current_identity] = lambda: user_id
        app.dependency_overrides[get_current_identity_optional] = lambda: user_id
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield {"app": app, "make_rest_client": make_rest_client}


def _ws_client(app: object) -> TestClient:
    return TestClient(app)  # type: ignore[arg-type]


async def test_a_websocket_message_is_relayed_to_redis_with_the_user_id_stamped(
    unique_name: str,
) -> None:
    """Proves the websocket -> Redis half of the relay, plus the
    security-relevant stamping (never trusting a client-supplied
    `user_id`) — driving `run_relay_loop` directly against a fake
    `WebSocketLike` and real Redis, entirely on the test's own event
    loop (no `TestClient`/real-WS-transport involved; see this module's
    docstring for why).
    """
    channel = f"workflow:collab-relay-{unique_name}:collab"

    # A plain subscriber, standing in for another API instance's own
    # relay loop, that would see this published through Redis.
    subscriber: Redis = Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    pubsub = subscriber.pubsub()
    await pubsub.subscribe(channel)
    await pubsub.get_message(timeout=1)  # the subscribe-confirmation message, not real data

    redis: Redis = Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    ws = _FakeWebSocket()
    relay_task = asyncio.create_task(
        run_relay_loop(ws, redis=redis, channel=channel, user_id="collab-owner-real-id")
    )

    ws.push(json.dumps({"type": "node_moved", "node_id": "n1", "x": 10, "y": 20}))

    message = None
    for _ in range(20):
        message = await pubsub.get_message(timeout=0.5)
        if message is not None and message["type"] == "message":
            break
    assert message is not None
    received = json.loads(message["data"])

    relay_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await relay_task
    await pubsub.unsubscribe(channel)
    await pubsub.aclose()  # type: ignore[no-untyped-call]
    await subscriber.aclose()
    await redis.aclose()

    assert received["type"] == "node_moved"
    assert received["node_id"] == "n1"
    # Stamped server-side from the resolved ticket — never trusted from
    # the client's own payload, which sent no user_id at all.
    assert received["user_id"] == "collab-owner-real-id"


async def test_a_redis_publish_is_relayed_to_the_websocket(unique_name: str) -> None:
    """Proves the Redis -> websocket half of the relay: a message
    published by another API instance (simulated here by a plain
    publisher on the test's own event loop) reaches this connection.
    """
    channel = f"workflow:collab-relay-{unique_name}:collab"

    redis: Redis = Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    ws = _FakeWebSocket()
    relay_task = asyncio.create_task(
        run_relay_loop(ws, redis=redis, channel=channel, user_id="collab-owner-real-id")
    )

    publisher: Redis = Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    published = json.dumps({"type": "cursor", "user_id": "someone-else"})
    delivered = None
    for _ in range(20):
        await publisher.publish(channel, published)
        await asyncio.sleep(0.1)
        if ws.sent:
            delivered = ws.sent[0]
            break

    relay_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await relay_task
    await publisher.aclose()
    await redis.aclose()

    assert delivered is not None
    assert json.loads(delivered) == {"type": "cursor", "user_id": "someone-else"}


async def test_a_stale_ticket_is_rejected(
    db_session: AsyncSession, harness: dict[str, object], unique_name: str
) -> None:
    user_id = f"collab-stale-{unique_name}"
    await _make_user(db_session, user_id)
    make_client: Callable[[str], AsyncClient] = harness["make_rest_client"]  # type: ignore[assignment]
    rest = make_client(user_id)

    create_ws = await rest.post("/api/v1/workspaces", json={"name": f"collab-stale-{unique_name}"})
    workspace_id = create_ws.json()["id"]
    create_wf = await rest.post(
        f"/api/v1/workspaces/{workspace_id}/workflows",
        json={"name": "Stale Ticket Test", "description": None},
    )
    workflow_id = create_wf.json()["workflow"]["id"]

    client = _ws_client(harness["app"])
    bad_url = (
        f"/api/v1/workspaces/{workspace_id}/workflows/{workflow_id}/collab?ticket=not-a-real-ticket"
    )
    with pytest.raises(Exception), client.websocket_connect(bad_url):  # noqa: B017,PT011
        pass
