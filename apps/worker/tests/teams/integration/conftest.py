"""Integration fixtures for the team runtime — real Postgres, never
mocked (CLAUDE.md §11).

Both things under test here are exactly the kind a fake cannot prove
correct: `PostgresTeamSession` depends on a real identity column for
ordering and on partition pruning for `pop_item`, and
`SharedMemoryStore` depends on a real `UNIQUE NULLS NOT DISTINCT`
constraint for its upsert. An in-memory double would pass while both
were broken.

Two workspaces are seeded, not one, so cross-tenant assertions have a
real second tenant to be isolated *from* rather than asserting against
an empty table.
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
    # Function-scoped: an async engine's pool binds to the loop that
    # created it, and pytest-asyncio gives each test its own loop.
    engine = create_async_engine(_require_database_url(), pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def team_fixture(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[dict[str, str]]:
    """Two workspaces, each with a team, agents, and an open session.

    `agent_a1` and `agent_b1` are published; `agent_a2` deliberately is
    not, so the repository's "only runnable members" rule has an
    unpublished agent to actually exclude rather than being asserted
    against a table where every row qualifies.
    """
    now = datetime.now(UTC)
    user_id = str(uuid.uuid4())
    ids = {
        "user_id": user_id,
        "ws_a": str(uuid.uuid4()),
        "ws_b": str(uuid.uuid4()),
        "team_a": str(uuid.uuid4()),
        "team_b": str(uuid.uuid4()),
        "agent_a1": str(uuid.uuid4()),
        "agent_a2": str(uuid.uuid4()),
        "agent_b1": str(uuid.uuid4()),
        "session_a": str(uuid.uuid4()),
        "session_a2": str(uuid.uuid4()),
        "session_b": str(uuid.uuid4()),
    }

    async with session_factory() as db:
        await db.execute(
            text(
                "INSERT INTO users (id, email, name, email_verified, created_at, updated_at) "
                "VALUES (:id, :email, 'team-int', false, :now, :now)"
            ),
            {"id": user_id, "email": f"{user_id}@example.test", "now": now},
        )
        for ws_key in ("ws_a", "ws_b"):
            await db.execute(
                text(
                    "INSERT INTO workspaces (id, name, slug, created_at) "
                    "VALUES (:id, :name, :slug, :now)"
                ),
                {
                    "id": ids[ws_key],
                    "name": f"ws-{ids[ws_key][:8]}",
                    "slug": f"ws-{ids[ws_key][:8]}",
                    "now": now,
                },
            )
        for agent_key, ws_key in (
            ("agent_a1", "ws_a"),
            ("agent_a2", "ws_a"),
            ("agent_b1", "ws_b"),
        ):
            await db.execute(
                text(
                    "INSERT INTO agents (id, workspace_id, name, status, created_by_user_id, "
                    " created_at, updated_at) "
                    "VALUES (:id, :ws, :name, 'draft', :user, :now, :now)"
                ),
                {
                    "id": ids[agent_key],
                    "ws": ids[ws_key],
                    "name": agent_key,
                    "user": user_id,
                    "now": now,
                },
            )
        # Only a1 and b1 get a published version; a2 stays a draft.
        for agent_key in ("agent_a1", "agent_b1"):
            version_id = str(uuid.uuid4())
            ids[f"version_{agent_key}"] = version_id
            await db.execute(
                text(
                    "INSERT INTO agent_versions (id, agent_id, version_number, config, "
                    " created_by_user_id, created_at) "
                    "VALUES (:id, :agent, 1, :config, :user, :now)"
                ),
                {
                    "id": version_id,
                    "agent": ids[agent_key],
                    "config": (
                        '{"name": "' + agent_key + '", "model": "gpt-4o-mini", '
                        '"system_instructions": "Be helpful.", "tools": []}'
                    ),
                    "user": user_id,
                    "now": now,
                },
            )
            await db.execute(
                text(
                    "UPDATE agents SET published_version_id = :v, status = 'active' WHERE id = :id"
                ),
                {"v": version_id, "id": ids[agent_key]},
            )

        for team_key, ws_key in (("team_a", "ws_a"), ("team_b", "ws_b")):
            await db.execute(
                text(
                    "INSERT INTO teams (id, workspace_id, name, topology, max_turns, "
                    " max_cost_micro_usd, timeout_seconds, shared_memory_enabled, "
                    " shared_knowledge_base_ids, created_by_user_id, created_at, updated_at) "
                    "VALUES (:id, :ws, :name, 'sequential', 20, 1000000, 300, true, "
                    "        '[]'::jsonb, :user, :now, :now)"
                ),
                {
                    "id": ids[team_key],
                    "ws": ids[ws_key],
                    "name": team_key,
                    "user": user_id,
                    "now": now,
                },
            )
        # team_a gets both a published and an unpublished member; team_b
        # gets one published member.
        for member_key, team_key, ws_key, agent_key, role, position in (
            ("member_a1", "team_a", "ws_a", "agent_a1", "researcher", 0),
            ("member_a2", "team_a", "ws_a", "agent_a2", "writer", 1),
            ("member_b1", "team_b", "ws_b", "agent_b1", "supervisor", 0),
        ):
            ids[member_key] = str(uuid.uuid4())
            await db.execute(
                text(
                    "INSERT INTO team_members (id, team_id, workspace_id, agent_id, role, "
                    " position, can_receive_handoff, created_at) "
                    "VALUES (:id, :team, :ws, :agent, :role, :pos, true, :now)"
                ),
                {
                    "id": ids[member_key],
                    "team": ids[team_key],
                    "ws": ids[ws_key],
                    "agent": ids[agent_key],
                    "role": role,
                    "pos": position,
                    "now": now,
                },
            )

        for sess_key, team_key, ws_key in (
            ("session_a", "team_a", "ws_a"),
            ("session_a2", "team_a", "ws_a"),
            ("session_b", "team_b", "ws_b"),
        ):
            await db.execute(
                text(
                    "INSERT INTO team_sessions (id, workspace_id, team_id, status, input, "
                    " total_turns, created_at) "
                    "VALUES (:id, :ws, :team, 'running', '{}'::jsonb, 0, :now)"
                ),
                {
                    "id": ids[sess_key],
                    "ws": ids[ws_key],
                    "team": ids[team_key],
                    "now": now,
                },
            )
        await db.commit()

    yield ids

    async with session_factory() as db:
        # team_session_items is not FK-linked (it is partitioned, matching
        # execution_events), so it is cleaned explicitly rather than by
        # cascade from workspaces.
        await db.execute(
            text("DELETE FROM team_session_items WHERE workspace_id = ANY(:ids)"),
            {"ids": [ids["ws_a"], ids["ws_b"]]},
        )
        await db.execute(
            text("DELETE FROM workspaces WHERE id = ANY(:ids)"),
            {"ids": [ids["ws_a"], ids["ws_b"]]},
        )
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        await db.commit()
