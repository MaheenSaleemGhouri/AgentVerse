"""Integration tests for `WorkerTeamRepository` against real Postgres.

The load path is a three-table join (`team_members` → `agents` →
`agent_versions`) filtered on the agent's *published* version. That join
is the thing a fake cannot prove: a member whose agent has never been
published must not appear, and getting that wrong would run a team
against draft configuration the user never published.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentverse_worker.teams.repository import WorkerTeamRepository

pytestmark = pytest.mark.integration


class TestGetTeam:
    async def test_loads_the_team_with_its_published_members(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        async with session_factory() as db:
            team = await WorkerTeamRepository(db).get_team(
                team_fixture["team_a"], workspace_id=team_fixture["ws_a"]
            )
        assert team is not None
        assert team.topology == "sequential"
        assert [m.agent_id for m in team.ordered_members()] == [team_fixture["agent_a1"]]

    async def test_excludes_members_whose_agent_is_unpublished(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        """`agent_a2` is a member of team_a but has no published version.
        Including it would run a team against draft configuration."""
        async with session_factory() as db:
            team = await WorkerTeamRepository(db).get_team(
                team_fixture["team_a"], workspace_id=team_fixture["ws_a"]
            )
        assert team is not None
        assert team_fixture["agent_a2"] not in {m.agent_id for m in team.members}

    async def test_member_carries_the_agents_own_config(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        """A team composes agents; it never redefines them. The config a
        member runs with has to be the agent's own published one."""
        async with session_factory() as db:
            team = await WorkerTeamRepository(db).get_team(
                team_fixture["team_a"], workspace_id=team_fixture["ws_a"]
            )
        assert team is not None
        member = team.ordered_members()[0]
        assert member.config["model"] == "gpt-4o-mini"
        assert member.config["system_instructions"] == "Be helpful."
        assert member.agent_version_id == team_fixture["version_agent_a1"]

    async def test_another_workspace_cannot_load_the_team(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        """Rule 11: a team id alone is never enough. Cross-workspace
        access resolves to nothing rather than to data."""
        async with session_factory() as db:
            team = await WorkerTeamRepository(db).get_team(
                team_fixture["team_a"], workspace_id=team_fixture["ws_b"]
            )
        assert team is None

    async def test_soft_deleted_team_is_not_runnable(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        async with session_factory() as db:
            await db.execute(
                text("UPDATE teams SET deleted_at = now() WHERE id = :id"),
                {"id": team_fixture["team_a"]},
            )
            await db.commit()
            team = await WorkerTeamRepository(db).get_team(
                team_fixture["team_a"], workspace_id=team_fixture["ws_a"]
            )
        assert team is None


class TestWrites:
    async def test_status_transition_stamps_the_lifecycle_timestamps(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        async with session_factory() as db:
            repo = WorkerTeamRepository(db)
            await repo.update_session_status(session_id=team_fixture["session_a"], status="running")
            await repo.update_session_status(
                session_id=team_fixture["session_a"],
                status="success",
                output="done",
                cost_micro_usd=1234,
                total_turns=3,
            )
            row = (
                (
                    await db.execute(
                        text(
                            "SELECT status, output, cost_micro_usd, total_turns, started_at, "
                            "completed_at FROM team_sessions WHERE id = :id"
                        ),
                        {"id": team_fixture["session_a"]},
                    )
                )
                .mappings()
                .one()
            )
        assert row["status"] == "success"
        assert row["output"] == "done"
        assert row["cost_micro_usd"] == 1234
        assert row["total_turns"] == 3
        assert row["started_at"] is not None
        assert row["completed_at"] is not None

    async def test_handoff_round_trips_through_jsonb(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        async with session_factory() as db:
            repo = WorkerTeamRepository(db)
            handoff_id = await repo.record_handoff(
                session_id=team_fixture["session_a"],
                workspace_id=team_fixture["ws_a"],
                from_agent_id=team_fixture["agent_a1"],
                to_agent_id=team_fixture["agent_a2"],
                kind="manual",
                contract={"schema_version": 1, "summary": "did the research"},
                reason="stage transition",
                sequence=1,
            )
            row = (
                (
                    await db.execute(
                        text("SELECT kind, contract FROM handoffs WHERE id = :id"),
                        {"id": handoff_id},
                    )
                )
                .mappings()
                .one()
            )
        assert row["kind"] == "manual"
        assert row["contract"]["summary"] == "did the research"

    async def test_execution_events_land_in_the_partitioned_table(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        async with session_factory() as db:
            await WorkerTeamRepository(db).record_event(
                session_id=team_fixture["session_a"],
                workspace_id=team_fixture["ws_a"],
                event_type="agent_started",
                agent_id=team_fixture["agent_a1"],
                sequence=1,
                payload={"stage": "researcher"},
                cost_micro_usd=None,
            )
            count = await db.scalar(
                text("SELECT count(*) FROM execution_events WHERE session_id = :id"),
                {"id": team_fixture["session_a"]},
            )
        assert count == 1

    async def test_communication_log_records_the_typed_kind(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        async with session_factory() as db:
            await WorkerTeamRepository(db).record_communication(
                session_id=team_fixture["session_a"],
                workspace_id=team_fixture["ws_a"],
                from_agent_id=team_fixture["agent_a1"],
                to_agent_id=None,
                kind="task_result",
                content={"output": "done"},
                sequence=1,
            )
            row = (
                (
                    await db.execute(
                        text("SELECT kind, content FROM communication_logs WHERE session_id = :id"),
                        {"id": team_fixture["session_a"]},
                    )
                )
                .mappings()
                .one()
            )
        assert row["kind"] == "task_result"
        assert row["content"]["output"] == "done"
