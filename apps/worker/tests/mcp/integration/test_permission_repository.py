"""`WorkerIntegrationRepository.resolve_for_agent` against real Postgres.

Written alongside the `fallback_tools` migration (gap #2,
`docs/PHASE-6-MCP-CHECKLIST.md`): the SELECT that builds a `ToolGrant`
is hand-written `sqlalchemy.select(...).add_columns(...)` reaching
across `installed_servers`/`mcp_servers`/`workspace_integrations`/
`permissions`, and a wrong column or join there is exactly the kind of
mistake `ruff`/`mypy` cannot catch — only a real query against a real
schema can.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from agentverse_shared.security.envelope import CredentialVault, KeyRing
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from agentverse_worker.mcp.repository import WorkerIntegrationRepository

pytestmark = pytest.mark.integration

_DATABASE_URL = os.environ.get("AGENTVERSE_WORKER_DATABASE_URL")


def _require_database_url() -> str:
    if not _DATABASE_URL:
        pytest.skip(
            "AGENTVERSE_WORKER_DATABASE_URL not set — integration tests need a real Postgres"
        )
    return _DATABASE_URL


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_require_database_url(), pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def workspace_with_permission(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[dict[str, str]]:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    ids = {
        "workspace_id": str(uuid.uuid4()),
        "installed_server_id": str(uuid.uuid4()),
        "permission_id": str(uuid.uuid4()),
    }

    async with session_factory() as db:
        await db.execute(
            text("INSERT INTO workspaces (id, name, slug, created_at) VALUES (:id, :n, :s, :now)"),
            {
                "id": ids["workspace_id"],
                "n": "permission-repo-test",
                "s": ids["workspace_id"][:8],
                "now": now,
            },
        )
        await db.execute(
            text(
                "INSERT INTO installed_servers "
                "(id, workspace_id, mcp_server_id, display_name, transport, status, health, "
                " config, discovered_tools, created_at, updated_at) "
                "VALUES (:id, :ws, NULL, 'Test Server', 'streamable_http', 'active', 'healthy', "
                " '{}', '[]', :now, :now)"
            ),
            {"id": ids["installed_server_id"], "ws": ids["workspace_id"], "now": now},
        )
        await db.execute(
            text(
                "INSERT INTO permissions "
                "(id, workspace_id, installed_server_id, agent_id, team_id, level, "
                " allowed_tools, timeout_seconds, max_retries, cache_ttl_seconds, "
                " max_calls_per_run, priority, fallback_tools, created_at, updated_at) "
                "VALUES (:id, :ws, :server, NULL, NULL, 'read_write', '[]', 30, 2, 0, 50, 0, "
                " :fallback_tools, :now, :now)"
            ),
            {
                "id": ids["permission_id"],
                "ws": ids["workspace_id"],
                "server": ids["installed_server_id"],
                "fallback_tools": '{"list_issues": "search_issues"}',
                "now": now,
            },
        )
        await db.commit()

    yield ids

    async with session_factory() as db:
        await db.execute(
            text("DELETE FROM permissions WHERE id = :id"), {"id": ids["permission_id"]}
        )
        await db.execute(
            text("DELETE FROM installed_servers WHERE id = :id"),
            {"id": ids["installed_server_id"]},
        )
        await db.execute(text("DELETE FROM workspaces WHERE id = :id"), {"id": ids["workspace_id"]})
        await db.commit()


async def test_resolve_for_agent_carries_fallback_tools_into_the_grant(
    session_factory: async_sessionmaker[AsyncSession], workspace_with_permission: dict[str, str]
) -> None:
    vault = CredentialVault(KeyRing({"v1": os.urandom(32)}, "v1"))

    async with session_factory() as session:
        repo = WorkerIntegrationRepository(session, vault)
        resolved = await repo.resolve_for_agent(
            workspace_id=workspace_with_permission["workspace_id"],
            agent_id=str(uuid.uuid4()),
        )

    assert len(resolved) == 1
    assert resolved[0].grant.fallback_tools == {"list_issues": "search_issues"}
