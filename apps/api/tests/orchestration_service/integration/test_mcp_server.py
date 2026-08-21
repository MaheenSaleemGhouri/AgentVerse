"""AgentVerse's own MCP server surface (docs/adr/0017), tested through
the real MCP protocol — a real `mcp` client (Streamable HTTP transport,
over an in-process ASGI connection, no separate server process needed)
against the real FastAPI app, with a real `mcp_client`-kind API key
minted through the real `/mcp-clients` route. This is the kind of
transport/auth-wiring correctness a fake would let pass while broken
(CLAUDE.md §11) — nothing here is exercised anywhere else.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.infrastructure.models import User
from agentverse_api.auth_service.interface.dependencies.get_current_identity import (
    get_current_identity,
    get_current_identity_optional,
)
from agentverse_api.infrastructure.db import get_db_session, get_engine, get_session_factory
from agentverse_api.main import create_app
from agentverse_api.orchestration_service.interface.mcp_server.server import get_mcp_server

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _fresh_mcp_server() -> Iterator[None]:
    """`get_mcp_server()` is process-lifetime `@lru_cache`d (one real
    session manager for the app's whole life) — correct in production,
    where its `.run()` is entered exactly once by the app lifespan, but
    `StreamableHTTPSessionManager.run()` raises if entered a second time
    on the same instance, which every test after the first in this file
    would do against the cached singleton. Clearing the cache per test
    gives each test its own instance, matching how each is really a
    fresh process boundary in production (a new deploy), not a gap in
    the app's actual once-per-process contract.
    """
    get_mcp_server.cache_clear()
    yield
    get_mcp_server.cache_clear()


@pytest.fixture(autouse=True)
def _fresh_session_factory() -> Iterator[None]:
    """`get_engine()`/`get_session_factory()` (`infrastructure/db.py`)
    are the same kind of process-lifetime `@lru_cache` as `get_mcp_server`
    above, for the same production-correct reason — but
    `ApiKeyTokenVerifier` (`mcp_server/auth.py`) uses them directly,
    bypassing this file's `db_session_override`, so the cached engine's
    pooled asyncpg connections end up bound to whichever test's event
    loop was running when the engine was first created. pytest-asyncio
    gives each test function its own loop; a pooled connection created on
    an earlier test's (now-closed) loop surfaces as `RuntimeError: ...
    attached to a different loop` the next time the pool hands that
    specific connection back out — intermittent, since it only bites when
    the pool happens to return the stale one rather than a same-loop
    sibling from its own pool_size. Clearing *both* caches per test (the
    sessionmaker alone is not enough — it just wraps whatever engine
    `get_engine()` still has cached) gives each test its own engine and
    pool on its own loop, matching how `_fresh_mcp_server` above already
    treats the same class of cache for the same reason.
    """
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    yield
    get_engine.cache_clear()
    get_session_factory.cache_clear()


async def _make_user(session: AsyncSession, user_id: str) -> None:
    session.add(
        User(
            id=user_id,
            name=user_id,
            email=f"{user_id}@example.com",
            email_verified=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    await session.commit()


@pytest.fixture
async def rest_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """A real authenticated REST client, for setup only — creating the
    workspace/agent/credential the MCP protocol test below then drives.
    """
    user_id = f"mcp-e2e-owner-{uuid4()}"
    await _make_user(db_session, user_id)

    async def db_session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app = create_app()
    app.dependency_overrides[get_db_session] = db_session_override
    app.dependency_overrides[get_current_identity] = lambda: user_id
    app.dependency_overrides[get_current_identity_optional] = lambda: user_id
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    yield client
    await client.aclose()


async def _setup_workspace_agent_and_mcp_credential(
    rest_client: AsyncClient, db_session: AsyncSession, unique_name: str
) -> tuple[str, str, str]:
    """Returns (workspace_id, agent_id, mcp_client_plaintext_key).

    Commits `db_session` before returning: `rest_client`'s routes write
    through that shared, DI-overridden session (never committed by the
    override itself, unlike the real per-request `get_db_session`), but
    `ApiKeyTokenVerifier` (`mcp_server/auth.py`) deliberately opens its
    *own* connection via the real `get_session_factory()` — it is not
    itself FastAPI-DI-wired, since it is built once at app-construction
    time, not resolved per request. Without an explicit commit here, that
    separate connection cannot see the credential this just issued.

    Named per-test via `unique_name`, not a fixed literal: a repeated
    local run (or any future parallel run) against the same database
    would otherwise collide on the workspace name's unique slug.
    """
    create_ws = await rest_client.post(
        "/api/v1/workspaces", json={"name": f"MCP E2E {unique_name}"}
    )
    assert create_ws.status_code == 201
    workspace_id = create_ws.json()["id"]

    create_agent = await rest_client.post(
        f"/api/v1/workspaces/{workspace_id}/agents",
        json={
            "name": "Greeter",
            "description": None,
            "model": "gpt-4o-mini",
            "system_instructions": "Say hello.",
            "temperature": None,
            "max_output_tokens": None,
            "tools": [],
            "knowledge_base_ids": [],
        },
    )
    assert create_agent.status_code == 201, create_agent.text
    agent_id = create_agent.json()["agent"]["id"]

    publish = await rest_client.post(f"/api/v1/workspaces/{workspace_id}/agents/{agent_id}/publish")
    assert publish.status_code == 200, publish.text

    issue_key = await rest_client.post(
        f"/api/v1/workspaces/{workspace_id}/mcp-clients", json={"name": "test client"}
    )
    assert issue_key.status_code == 201, issue_key.text
    await db_session.commit()
    return workspace_id, agent_id, issue_key.json()["key"]


async def test_a_real_mcp_client_can_list_and_run_agents(
    rest_client: AsyncClient, db_session: AsyncSession, unique_name: str
) -> None:
    workspace_id, agent_id, mcp_key = await _setup_workspace_agent_and_mcp_credential(
        rest_client, db_session, unique_name
    )

    app = create_app()  # a fresh app object, matching how a real deployment mounts /mcp once
    async with (  # noqa: SIM117 - the tuple/session nesting reads clearer split
        get_mcp_server().session_manager.run(),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://localhost",
            headers={"Authorization": f"Bearer {mcp_key}"},
        ) as http_client,
        streamable_http_client("http://localhost/mcp", http_client=http_client) as (
            read_stream,
            write_stream,
            _get_session_id,
        ),
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = {t.name for t in tools.tools}
            assert {
                "list_agents",
                "get_agent",
                "run_agent_tool",
                "get_run_status",
                "list_workflows",
                "get_workflow",
                "run_workflow",
            } <= tool_names

            listed = await session.call_tool("list_agents", {})
            assert not listed.isError
            assert listed.structuredContent is not None
            agent_ids = {a["id"] for a in listed.structuredContent["result"]}
            assert agent_id in agent_ids

            fetched = await session.call_tool("get_agent", {"agent_id": agent_id})
            assert not fetched.isError
            assert fetched.structuredContent is not None
            assert fetched.structuredContent["id"] == agent_id

            ran = await session.call_tool(
                "run_agent_tool", {"agent_id": agent_id, "input": {"prompt": "hi"}}
            )
            assert not ran.isError, ran.content
            assert ran.structuredContent is not None
            run_id = ran.structuredContent["id"]

            status = await session.call_tool("get_run_status", {"run_id": run_id})
            assert not status.isError
            assert status.structuredContent is not None
            assert status.structuredContent["run_type"] == "agent"

    # The tool calls above wrote real audit_logs rows through the real
    # AuditService — not a side effect any fake could have faked into
    # existing.
    rows = (
        await db_session.execute(
            text(
                "SELECT action, outcome FROM audit_logs "
                "WHERE workspace_id = :ws AND action LIKE 'mcp_server.%' ORDER BY created_at"
            ),
            {"ws": workspace_id},
        )
    ).all()
    assert len(rows) >= 4
    assert all(r.outcome == "success" for r in rows)


async def test_a_user_api_key_is_rejected_by_the_mcp_server(
    rest_client: AsyncClient, db_session: AsyncSession, unique_name: str
) -> None:
    """`kind='user_api_key'` must never authenticate `/mcp` — the
    reverse of the ordinary-REST-API rejection already covered in
    `get_current_workspace` tests.
    """
    workspace_id, _agent_id, _mcp_key = await _setup_workspace_agent_and_mcp_credential(
        rest_client, db_session, unique_name
    )
    issue_user_key = await rest_client.post(
        f"/api/v1/workspaces/{workspace_id}/api-keys", json={"name": "personal key"}
    )
    assert issue_user_key.status_code == 201
    user_key = issue_user_key.json()["key"]
    await db_session.commit()

    app = create_app()
    with pytest.raises(Exception):  # noqa: B017 - the SDK raises a plain McpError/httpx error here
        async with (
            get_mcp_server().session_manager.run(),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://localhost",
                headers={"Authorization": f"Bearer {user_key}"},
            ) as http_client,
            streamable_http_client("http://localhost/mcp", http_client=http_client) as (
                read_stream,
                write_stream,
                _get_session_id,
            ),
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()


async def test_a_read_only_scoped_credential_cannot_run_an_agent(
    rest_client: AsyncClient, db_session: AsyncSession, unique_name: str
) -> None:
    workspace_id, agent_id, _mcp_key = await _setup_workspace_agent_and_mcp_credential(
        rest_client, db_session, unique_name
    )
    issue_readonly = await rest_client.post(
        f"/api/v1/workspaces/{workspace_id}/mcp-clients",
        json={"name": "readonly client", "scope": "read_only"},
    )
    assert issue_readonly.status_code == 201
    readonly_key = issue_readonly.json()["key"]
    await db_session.commit()

    app = create_app()
    async with (  # noqa: SIM117 - the tuple/session nesting reads clearer split
        get_mcp_server().session_manager.run(),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://localhost",
            headers={"Authorization": f"Bearer {readonly_key}"},
        ) as http_client,
        streamable_http_client("http://localhost/mcp", http_client=http_client) as (
            read_stream,
            write_stream,
            _get_session_id,
        ),
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # Reads still work.
            listed = await session.call_tool("list_agents", {})
            assert not listed.isError

            # A write is refused, not silently downgraded.
            denied = await session.call_tool(
                "run_agent_tool", {"agent_id": agent_id, "input": {"prompt": "hi"}}
            )
            assert denied.isError


async def test_create_support_ticket_and_escalate_to_human(
    rest_client: AsyncClient, db_session: AsyncSession, unique_name: str
) -> None:
    """Phase 13 — both tools create real `support_tickets` rows through
    the real application/repository layers, already `TRIAGED`, with no
    triage sub-run.
    """
    workspace_id, _agent_id, mcp_key = await _setup_workspace_agent_and_mcp_credential(
        rest_client, db_session, unique_name
    )

    app = create_app()
    async with (  # noqa: SIM117
        get_mcp_server().session_manager.run(),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://localhost",
            headers={"Authorization": f"Bearer {mcp_key}"},
        ) as http_client,
        streamable_http_client("http://localhost/mcp", http_client=http_client) as (
            read_stream,
            write_stream,
            _get_session_id,
        ),
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            ticket = await session.call_tool(
                "create_support_ticket",
                {
                    "subject": "Product arrived damaged",
                    "body": "The box was crushed.",
                    "category": "damaged-item",
                    "priority": "high",
                },
            )
            assert not ticket.isError, ticket.content
            assert ticket.structuredContent is not None
            assert ticket.structuredContent["status"] == "triaged"
            assert ticket.structuredContent["category"] == "damaged-item"
            assert "body" not in ticket.structuredContent  # Section 7: never the raw body back

            escalation = await session.call_tool(
                "escalate_to_human",
                {"reason": "refund dispute", "summary": "Customer disputes the decision."},
            )
            assert not escalation.isError, escalation.content
            assert escalation.structuredContent is not None
            assert escalation.structuredContent["category"] == "escalation"
            assert escalation.structuredContent["priority"] == "urgent"

    rows = (
        await db_session.execute(
            text("SELECT category, priority, status FROM support_tickets WHERE workspace_id = :ws"),
            {"ws": workspace_id},
        )
    ).all()
    assert {(r.category, r.priority, r.status) for r in rows} == {
        ("damaged-item", "high", "triaged"),
        ("escalation", "urgent", "triaged"),
    }
    audit_rows = (
        await db_session.execute(
            text(
                "SELECT action FROM audit_logs WHERE workspace_id = :ws "
                "AND action = 'mcp_server.tool_executed'"
            ),
            {"ws": workspace_id},
        )
    ).all()
    assert len(audit_rows) >= 2


async def test_commerce_tools_report_unavailable_without_a_real_integration(
    rest_client: AsyncClient, db_session: AsyncSession, unique_name: str
) -> None:
    """No commerce MCP integration exists in this test environment (or
    any environment today — ADR-0020) — these tools must say so plainly
    rather than inventing an order.
    """
    _workspace_id, _agent_id, mcp_key = await _setup_workspace_agent_and_mcp_credential(
        rest_client, db_session, unique_name
    )

    app = create_app()
    async with (  # noqa: SIM117
        get_mcp_server().session_manager.run(),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://localhost",
            headers={"Authorization": f"Bearer {mcp_key}"},
        ) as http_client,
        streamable_http_client("http://localhost/mcp", http_client=http_client) as (
            read_stream,
            write_stream,
            _get_session_id,
        ),
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            order = await session.call_tool("lookup_order", {"order_number": "NC-1024"})
            assert not order.isError
            assert order.structuredContent == {
                "available": False,
                "reason": "No commerce integration is installed for this workspace.",
            }

            shipping = await session.call_tool(
                "check_shipping_status", {"order_number": "NC-1024"}
            )
            assert not shipping.isError
            assert shipping.structuredContent is not None
            assert shipping.structuredContent["available"] is False

            # Neither tool's Python signature accepts workspace_id (or any
            # credential/URL/key) as a parameter at all — `resolve_context`
            # is the only source of `workspace_id` for any tool in this
            # file, so there is structurally nothing for a caller to
            # override here (Section 15's constraint). The stronger
            # "unexpected argument is refused" guarantee Section 15 also
            # asks for is `apps/worker/tools/boundary.py::validate_arguments`
            # (`additionalProperties: false`), which governs the *agent*
            # calling this tool through `GovernedMcpServer` — a different
            # layer from this raw MCP-protocol client, covered by
            # `apps/worker/tests/tools/test_boundary.py`, not re-tested
            # here.


async def test_request_return_always_routes_to_human_approval(
    rest_client: AsyncClient, db_session: AsyncSession, unique_name: str
) -> None:
    """Section 17: a return is never auto-processed, regardless of
    integration state — it always becomes an approval ticket.
    """
    workspace_id, _agent_id, mcp_key = await _setup_workspace_agent_and_mcp_credential(
        rest_client, db_session, unique_name
    )

    app = create_app()
    async with (  # noqa: SIM117
        get_mcp_server().session_manager.run(),
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://localhost",
            headers={"Authorization": f"Bearer {mcp_key}"},
        ) as http_client,
        streamable_http_client("http://localhost/mcp", http_client=http_client) as (
            read_stream,
            write_stream,
            _get_session_id,
        ),
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            result = await session.call_tool(
                "request_return", {"order_number": "NC-1024", "reason": "wrong item"}
            )
            assert not result.isError, result.content
            assert result.structuredContent is not None
            assert result.structuredContent["approval_required"] is True
            assert result.structuredContent["status"] == "triaged"

    rows = (
        await db_session.execute(
            text(
                "SELECT category FROM support_tickets WHERE workspace_id = :ws "
                "AND category = 'return-request'"
            ),
            {"ws": workspace_id},
        )
    ).all()
    assert len(rows) == 1
