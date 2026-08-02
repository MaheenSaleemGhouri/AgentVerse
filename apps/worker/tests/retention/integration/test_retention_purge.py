"""`purge_workspace` against a real Postgres.

Real Postgres, never mocked (CLAUDE.md §11): what is under test is the
cutoff subquery, the FK cascade that takes `agent_run_steps` with the
run, and the append to `audit_logs` — all three are exactly the kind of
thing a fake repository would happily let pass while broken.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from agentverse_worker.retention.sweep import MIN_RETENTION_DAYS, purge_workspace

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
async def session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


async def _seed_workspace(session: AsyncSession) -> tuple[str, str, str]:
    """Creates the user → workspace → agent → agent_version chain a run
    needs, and returns `(workspace_id, agent_id, agent_version_id)`.
    """
    suffix = uuid.uuid4().hex[:12]
    user_id = f"retention-user-{suffix}"
    workspace_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    await session.execute(
        text(
            "INSERT INTO users (id, name, email, email_verified, created_at, updated_at) "
            "VALUES (:id, :id, :email, false, :now, :now)"
        ),
        {"id": user_id, "email": f"{user_id}@example.com", "now": now},
    )
    await session.execute(
        text(
            "INSERT INTO workspaces (id, name, slug, created_at) "
            "VALUES (:id, :name, :slug, :now)"
        ),
        {"id": workspace_id, "name": f"ws-{suffix}", "slug": f"ws-{suffix}", "now": now},
    )
    await session.execute(
        text(
            "INSERT INTO agents (id, workspace_id, name, created_by_user_id, "
            "created_at, updated_at) VALUES (:id, :ws, :name, :user, :now, :now)"
        ),
        {
            "id": agent_id,
            "ws": workspace_id,
            "name": f"agent-{suffix}",
            "user": user_id,
            "now": now,
        },
    )
    await session.execute(
        text(
            "INSERT INTO agent_versions (id, agent_id, version_number, config, "
            "created_by_user_id, created_at) "
            "VALUES (:id, :agent, 1, '{}'::jsonb, :user, :now)"
        ),
        {"id": version_id, "agent": agent_id, "user": user_id, "now": now},
    )
    await session.commit()
    return workspace_id, agent_id, version_id


async def _insert_run(
    session: AsyncSession,
    *,
    workspace_id: str,
    agent_id: str,
    version_id: str,
    created_at: datetime,
) -> str:
    run_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO agent_runs (id, workspace_id, agent_id, agent_version_id, "
            "status, input, created_at) "
            "VALUES (:id, :ws, :agent, :version, 'success', '{}'::jsonb, :created_at)"
        ),
        {
            "id": run_id,
            "ws": workspace_id,
            "agent": agent_id,
            "version": version_id,
            "created_at": created_at,
        },
    )
    await session.commit()
    return run_id


async def _run_ids(session: AsyncSession, workspace_id: str) -> set[str]:
    result = await session.execute(
        text("SELECT id FROM agent_runs WHERE workspace_id = :ws"), {"ws": workspace_id}
    )
    return {str(row[0]) for row in result.all()}


async def test_purges_runs_past_the_cutoff_and_keeps_the_rest(session: AsyncSession) -> None:
    workspace_id, agent_id, version_id = await _seed_workspace(session)
    now = datetime.now(UTC)

    old = await _insert_run(
        session,
        workspace_id=workspace_id,
        agent_id=agent_id,
        version_id=version_id,
        created_at=now - timedelta(days=45),
    )
    recent = await _insert_run(
        session,
        workspace_id=workspace_id,
        agent_id=agent_id,
        version_id=version_id,
        created_at=now - timedelta(days=3),
    )

    deleted = await purge_workspace(
        session, workspace_id=workspace_id, retention_days=30, batch_size=1000
    )

    assert deleted == 1
    remaining = await _run_ids(session, workspace_id)
    assert old not in remaining
    assert recent in remaining


async def test_purging_a_run_takes_its_steps_with_it(session: AsyncSession) -> None:
    """`agent_run_steps` cascades from `agent_runs`. If that FK ever
    changed to RESTRICT/SET NULL, this purge would either fail loudly or
    silently orphan trace rows — both worth catching here rather than in
    production.
    """
    workspace_id, agent_id, version_id = await _seed_workspace(session)
    created_at = datetime.now(UTC) - timedelta(days=60)
    run_id = await _insert_run(
        session,
        workspace_id=workspace_id,
        agent_id=agent_id,
        version_id=version_id,
        created_at=created_at,
    )
    await session.execute(
        text(
            "INSERT INTO agent_run_steps (id, run_id, workspace_id, sequence, "
            "step_type, payload, created_at) "
            "VALUES (:id, :run, :ws, 0, 'llm_call', '{}'::jsonb, :created_at)"
        ),
        {
            "id": str(uuid.uuid4()),
            "run": run_id,
            "ws": workspace_id,
            "created_at": created_at,
        },
    )
    await session.commit()

    await purge_workspace(
        session, workspace_id=workspace_id, retention_days=30, batch_size=1000
    )

    steps = await session.execute(
        text("SELECT count(*) FROM agent_run_steps WHERE run_id = :run"), {"run": run_id}
    )
    assert steps.scalar_one() == 0


async def test_a_purge_records_itself_in_the_append_only_audit_log(
    session: AsyncSession,
) -> None:
    workspace_id, agent_id, version_id = await _seed_workspace(session)
    await _insert_run(
        session,
        workspace_id=workspace_id,
        agent_id=agent_id,
        version_id=version_id,
        created_at=datetime.now(UTC) - timedelta(days=90),
    )

    await purge_workspace(
        session, workspace_id=workspace_id, retention_days=7, batch_size=1000
    )

    result = await session.execute(
        text(
            "SELECT action, outcome, metadata FROM audit_logs "
            "WHERE workspace_id = :ws AND action = 'retention.purged'"
        ),
        {"ws": workspace_id},
    )
    row = result.one()
    assert row[0] == "retention.purged"
    assert row[1] == "success"
    assert row[2]["deleted_runs"] == "1"


async def test_a_purge_never_reaches_another_workspace(session: AsyncSession) -> None:
    mine_ws, mine_agent, mine_version = await _seed_workspace(session)
    theirs_ws, theirs_agent, theirs_version = await _seed_workspace(session)
    ancient = datetime.now(UTC) - timedelta(days=365)

    await _insert_run(
        session,
        workspace_id=mine_ws,
        agent_id=mine_agent,
        version_id=mine_version,
        created_at=ancient,
    )
    theirs_run = await _insert_run(
        session,
        workspace_id=theirs_ws,
        agent_id=theirs_agent,
        version_id=theirs_version,
        created_at=ancient,
    )

    await purge_workspace(session, workspace_id=mine_ws, retention_days=1, batch_size=1000)

    assert await _run_ids(session, theirs_ws) == {theirs_run}


async def test_a_zero_day_retention_is_clamped_not_honoured(session: AsyncSession) -> None:
    """A `retention_days` of 0 (or negative) is treated as
    `MIN_RETENTION_DAYS`, so a typo cannot wipe today's runs.
    """
    workspace_id, agent_id, version_id = await _seed_workspace(session)
    today = await _insert_run(
        session,
        workspace_id=workspace_id,
        agent_id=agent_id,
        version_id=version_id,
        created_at=datetime.now(UTC),
    )

    deleted = await purge_workspace(
        session, workspace_id=workspace_id, retention_days=0, batch_size=1000
    )

    assert deleted == 0
    assert today in await _run_ids(session, workspace_id)
    assert MIN_RETENTION_DAYS >= 1
