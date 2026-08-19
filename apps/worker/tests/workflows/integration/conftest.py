"""Integration fixtures for the workflow engine — real Postgres, never
mocked (CLAUDE.md §11). Mirrors `tests/teams/integration/conftest.py`.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

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
async def workflow_fixture(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[dict[str, str]]:
    """One workspace, one published agent, and a two-node workflow
    (`agent_step` n1 -> `human_approval` n2) with a published version,
    plus a queued `workflow_runs` row targeting node n1.
    """
    now = datetime.now(UTC)
    ids = {k: str(uuid.uuid4()) for k in (
        "user_id", "ws_id", "agent_id", "version_id", "workflow_id", "workflow_version_id",
        "node1_id", "node2_id", "edge_id", "run_id",
    )}

    async with session_factory() as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, name, email_verified, created_at, updated_at) "
                "VALUES (:id, :email, 'wf-int', false, :now, :now)"
            ),
            {"id": ids["user_id"], "email": f"{ids['user_id']}@example.test", "now": now},
        )
        await db.execute(
            text(
                "INSERT INTO workspaces (id, name, slug, created_at) "
                "VALUES (:id, :name, :slug, :now)"
            ),
            {"id": ids["ws_id"], "name": "wf-ws", "slug": f"ws-{ids['ws_id'][:8]}", "now": now},
        )
        await db.execute(
            text(
                "INSERT INTO agents (id, workspace_id, name, status, "
                " created_by_user_id, created_at, updated_at) "
                "VALUES (:id, :ws, 'WF Agent', 'draft', :user, :now, :now)"
            ),
            {"id": ids["agent_id"], "ws": ids["ws_id"], "user": ids["user_id"], "now": now},
        )
        await db.execute(
            text(
                "INSERT INTO agent_versions (id, agent_id, version_number, config, "
                " created_by_user_id, created_at) "
                "VALUES (:id, :agent, 1, :config, :user, :now)"
            ),
            {
                "id": ids["version_id"], "agent": ids["agent_id"],
                "config": '{"model": "gpt-4o-mini", "system_instructions": "Be helpful.", '
                          '"tools": []}',
                "user": ids["user_id"], "now": now,
            },
        )
        await db.execute(
            text(
                "UPDATE agents SET published_version_id = :v, status = 'active' WHERE id = :id"
            ),
            {"v": ids["version_id"], "id": ids["agent_id"]},
        )
        await db.execute(
            text(
                "INSERT INTO workflows (id, workspace_id, name, status, "
                " created_by_user_id, created_at, updated_at) "
                "VALUES (:id, :ws, 'WF Test', 'draft', :user, :now, :now)"
            ),
            {"id": ids["workflow_id"], "ws": ids["ws_id"], "user": ids["user_id"], "now": now},
        )
        await db.execute(
            text(
                "INSERT INTO workflow_versions (id, workflow_id, version_number, "
                " created_by_user_id, created_at) VALUES (:id, :wf, 1, :user, :now)"
            ),
            {
                "id": ids["workflow_version_id"], "wf": ids["workflow_id"], "user": ids["user_id"],
                "now": now,
            },
        )
        await db.execute(
            text(
                "UPDATE workflows SET published_version_id = :v, status = 'active' WHERE id = :id"
            ),
            {"v": ids["workflow_version_id"], "id": ids["workflow_id"]},
        )
        await db.execute(
            text(
                "INSERT INTO workflow_nodes (id, workflow_version_id, type, position_x, "
                " position_y, config, agent_id, team_id) "
                "VALUES (:id, :wv, 'agent_step', 0, 0, '{}', :agent, NULL)"
            ),
            {"id": ids["node1_id"], "wv": ids["workflow_version_id"], "agent": ids["agent_id"]},
        )
        await db.execute(
            text(
                "INSERT INTO workflow_nodes (id, workflow_version_id, type, position_x, "
                " position_y, config, agent_id, team_id) "
                "VALUES (:id, :wv, 'human_approval', 100, 0, '{}', NULL, NULL)"
            ),
            {"id": ids["node2_id"], "wv": ids["workflow_version_id"]},
        )
        await db.execute(
            text(
                "INSERT INTO workflow_edges (id, workflow_version_id, from_node_id, to_node_id, "
                " condition, branch_order) "
                "VALUES (:id, :wv, :from_id, :to_id, NULL, NULL)"
            ),
            {
                "id": ids["edge_id"], "wv": ids["workflow_version_id"],
                "from_id": ids["node1_id"], "to_id": ids["node2_id"],
            },
        )
        await db.execute(
            text(
                "INSERT INTO workflow_runs (id, workspace_id, workflow_id, workflow_version_id, "
                " status, input, created_at) "
                "VALUES (:id, :ws, :wf, :wv, 'queued', '{\"prompt\": \"hello\"}', :now)"
            ),
            {
                "id": ids["run_id"], "ws": ids["ws_id"], "wf": ids["workflow_id"],
                "wv": ids["workflow_version_id"], "now": now,
            },
        )
        await db.commit()

    yield ids
