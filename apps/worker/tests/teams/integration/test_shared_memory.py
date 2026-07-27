"""Integration tests for `SharedMemoryStore` against real Postgres.

Two behaviors here are only real against a real database: the upsert
depends on `UNIQUE NULLS NOT DISTINCT` (with Postgres's default NULL
handling, every team-scoped write would append instead of update, and no
error would be raised), and the scope-precedence read depends on a real
`CASE` ordering. Both would pass against an in-memory dict while broken
in production.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentverse_worker.teams.shared_memory import (
    MAX_KEY_CHARS,
    MAX_VALUE_BYTES,
    SharedMemoryError,
    SharedMemoryStore,
)

pytestmark = pytest.mark.integration


def _store(
    factory: async_sessionmaker[AsyncSession],
    ids: dict[str, str],
    *,
    workspace_key: str = "ws_a",
    team_key: str = "team_a",
    session_key: str = "session_a",
    sharing_enabled: bool = True,
) -> SharedMemoryStore:
    return SharedMemoryStore(
        session_factory=factory,
        workspace_id=ids[workspace_key],
        team_id=ids[team_key],
        team_session_id=ids[session_key],
        sharing_enabled=sharing_enabled,
    )


class TestUpsert:
    async def test_writes_and_reads_back(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        store = _store(session_factory, team_fixture)
        await store.remember(
            agent_id=team_fixture["agent_a1"], key="plan", value={"steps": 3}, scope="team"
        )
        assert await store.recall(agent_id=team_fixture["agent_a2"], key="plan") == {"steps": 3}

    @pytest.mark.parametrize("scope", ["team", "session", "agent"])
    async def test_second_write_updates_rather_than_appends(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        team_fixture: dict[str, str],
        scope: str,
    ) -> None:
        """The regression this guards: `session_id`/`agent_id` are null
        at the wider scopes, and Postgres's default UNIQUE treats each
        NULL as distinct — so without NULLS NOT DISTINCT the upsert
        silently becomes an append and `recall` starts returning whichever
        duplicate the planner happens to pick."""
        store = _store(session_factory, team_fixture)
        agent_id = team_fixture["agent_a1"]
        await store.remember(agent_id=agent_id, key="k", value={"v": 1}, scope=scope)
        await store.remember(agent_id=agent_id, key="k", value={"v": 2}, scope=scope)

        assert await store.recall(agent_id=agent_id, key="k") == {"v": 2}
        async with session_factory() as db:
            count = await db.scalar(
                text("SELECT count(*) FROM shared_memory WHERE team_id = :t AND key = 'k'"),
                {"t": team_fixture["team_a"]},
            )
        assert count == 1

    async def test_recall_of_missing_key_returns_none(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        store = _store(session_factory, team_fixture)
        assert await store.recall(agent_id=team_fixture["agent_a1"], key="nope") is None


class TestScopeVisibility:
    async def test_team_scope_is_readable_across_sessions(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        """Team scope outliving a session is what distinguishes it from
        session scope — if it did not, the two would be the same thing."""
        first = _store(session_factory, team_fixture, session_key="session_a")
        second = _store(session_factory, team_fixture, session_key="session_a2")
        await first.remember(
            agent_id=team_fixture["agent_a1"], key="charter", value={"x": 1}, scope="team"
        )
        assert await second.recall(agent_id=team_fixture["agent_a2"], key="charter") == {"x": 1}

    async def test_session_scope_does_not_leak_to_another_session(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        first = _store(session_factory, team_fixture, session_key="session_a")
        second = _store(session_factory, team_fixture, session_key="session_a2")
        await first.remember(
            agent_id=team_fixture["agent_a1"], key="draft", value={"x": 1}, scope="session"
        )
        assert await second.recall(agent_id=team_fixture["agent_a1"], key="draft") is None

    async def test_agent_scope_is_private_to_the_writer(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        """Without this, `agent` scope would be decorative — the label
        would claim privacy the storage did not provide."""
        store = _store(session_factory, team_fixture)
        await store.remember(
            agent_id=team_fixture["agent_a1"], key="scratch", value={"x": 1}, scope="agent"
        )
        assert await store.recall(agent_id=team_fixture["agent_a1"], key="scratch") == {"x": 1}
        assert await store.recall(agent_id=team_fixture["agent_a2"], key="scratch") is None

    async def test_narrowest_scope_wins_when_a_key_exists_at_several(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        store = _store(session_factory, team_fixture)
        agent_id = team_fixture["agent_a1"]
        await store.remember(agent_id=agent_id, key="note", value={"from": "team"}, scope="team")
        await store.remember(
            agent_id=agent_id, key="note", value={"from": "session"}, scope="session"
        )
        await store.remember(agent_id=agent_id, key="note", value={"from": "agent"}, scope="agent")
        assert await store.recall(agent_id=agent_id, key="note") == {"from": "agent"}
        # A different member sees the session-scoped one, not the other
        # agent's private note.
        assert await store.recall(agent_id=team_fixture["agent_a2"], key="note") == {
            "from": "session"
        }

    async def test_list_keys_shows_only_readable_entries(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        store = _store(session_factory, team_fixture)
        await store.remember(
            agent_id=team_fixture["agent_a1"], key="shared", value={}, scope="team"
        )
        await store.remember(
            agent_id=team_fixture["agent_a1"], key="private", value={}, scope="agent"
        )
        assert await store.list_keys(agent_id=team_fixture["agent_a1"]) == ["private", "shared"]
        assert await store.list_keys(agent_id=team_fixture["agent_a2"]) == ["shared"]


class TestSharingDisabled:
    async def test_writes_collapse_to_agent_scope(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        store = _store(session_factory, team_fixture, sharing_enabled=False)
        effective = await store.remember(
            agent_id=team_fixture["agent_a1"], key="k", value={"v": 1}, scope="team"
        )
        assert effective == "agent"

    async def test_members_cannot_read_each_other(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        store = _store(session_factory, team_fixture, sharing_enabled=False)
        await store.remember(agent_id=team_fixture["agent_a1"], key="k", value={"v": 1})
        assert await store.recall(agent_id=team_fixture["agent_a1"], key="k") == {"v": 1}
        assert await store.recall(agent_id=team_fixture["agent_a2"], key="k") is None


class TestTenantIsolation:
    async def test_another_workspace_cannot_read_the_entry(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        owner = _store(session_factory, team_fixture)
        await owner.remember(
            agent_id=team_fixture["agent_a1"], key="secret", value={"v": 1}, scope="team"
        )
        intruder = _store(
            session_factory,
            team_fixture,
            workspace_key="ws_b",
            team_key="team_b",
            session_key="session_b",
        )
        assert await intruder.recall(agent_id=team_fixture["agent_b1"], key="secret") is None
        assert await intruder.list_keys(agent_id=team_fixture["agent_b1"]) == []

    async def test_another_team_in_the_same_workspace_cannot_read_it(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        """Workspace scoping alone is not enough — two teams in one
        workspace are still separate memories."""
        owner = _store(session_factory, team_fixture)
        await owner.remember(
            agent_id=team_fixture["agent_a1"], key="secret", value={"v": 1}, scope="team"
        )
        other_team = SharedMemoryStore(
            session_factory=session_factory,
            workspace_id=team_fixture["ws_a"],
            team_id=team_fixture["team_b"],
            team_session_id=team_fixture["session_a"],
        )
        assert await other_team.recall(agent_id=team_fixture["agent_a1"], key="secret") is None


class TestBounds:
    async def test_rejects_empty_key(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        store = _store(session_factory, team_fixture)
        with pytest.raises(SharedMemoryError, match="key"):
            await store.remember(agent_id=team_fixture["agent_a1"], key="  ", value={})

    async def test_rejects_oversized_key(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        store = _store(session_factory, team_fixture)
        with pytest.raises(SharedMemoryError, match="key"):
            await store.remember(
                agent_id=team_fixture["agent_a1"], key="k" * (MAX_KEY_CHARS + 1), value={}
            )

    async def test_rejects_oversized_value(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        """Values are model output. Without a cap, one member can write
        an arbitrarily large blob that every later `recall` pays for."""
        store = _store(session_factory, team_fixture)
        with pytest.raises(SharedMemoryError, match="exceeds"):
            await store.remember(
                agent_id=team_fixture["agent_a1"],
                key="big",
                value={"blob": "x" * (MAX_VALUE_BYTES + 100)},
            )

    async def test_rejects_unknown_scope(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        store = _store(session_factory, team_fixture)
        with pytest.raises(SharedMemoryError, match="scope"):
            await store.remember(
                agent_id=team_fixture["agent_a1"], key="k", value={}, scope="everyone"
            )
