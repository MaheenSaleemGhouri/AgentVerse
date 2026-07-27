"""Integration tests for `PostgresTeamSession` against real Postgres.

The point of this class is durability across worker instances, so the
tests construct *separate* session objects over the same branch wherever
that is what a second instance would do — asserting through one long-lived
object would prove nothing the SDK's in-memory session doesn't already do.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.items import TResponseInputItem
from agentverse_worker.teams.session import PostgresTeamSession

pytestmark = pytest.mark.integration


def _msg(text: str, role: str = "user") -> TResponseInputItem:
    return cast(TResponseInputItem, {"role": role, "content": text})


def _texts(items: list[TResponseInputItem]) -> list[str]:
    return [cast(dict[str, Any], item)["content"] for item in items]


def _session(
    factory: async_sessionmaker[AsyncSession],
    ids: dict[str, str],
    *,
    session_key: str = "session_a",
    agent_key: str | None = "agent_a1",
    workspace_key: str = "ws_a",
) -> PostgresTeamSession:
    return PostgresTeamSession(
        team_session_id=ids[session_key],
        workspace_id=ids[workspace_key],
        agent_id=ids[agent_key] if agent_key else None,
        session_factory=factory,
    )


class TestOrdering:
    async def test_returns_items_in_the_order_they_were_added(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        session = _session(session_factory, team_fixture)
        await session.add_items([_msg("first"), _msg("second")])
        await session.add_items([_msg("third")])
        assert _texts(await session.get_items()) == ["first", "second", "third"]

    async def test_limit_returns_the_latest_n_still_in_order(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        """The protocol asks for the *latest* N in chronological order.
        Taking the first N instead would silently replay the oldest turns
        into every subsequent model call."""
        session = _session(session_factory, team_fixture)
        await session.add_items([_msg("a"), _msg("b"), _msg("c"), _msg("d")])
        assert _texts(await session.get_items(limit=2)) == ["c", "d"]

    async def test_ordering_survives_a_same_timestamp_batch(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        """Every row in one `add_items` call shares a `created_at`, so
        ordering has to come from the identity column. If it came from
        the timestamp, a multi-item turn would come back shuffled."""
        session = _session(session_factory, team_fixture)
        expected = [f"item-{i:02d}" for i in range(25)]
        await session.add_items([_msg(t) for t in expected])
        assert _texts(await session.get_items()) == expected


class TestDurability:
    async def test_a_second_session_object_sees_the_same_history(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        """This is the whole reason the class exists: a follow-up turn
        picked up by a different worker instance must not start blank."""
        await _session(session_factory, team_fixture).add_items([_msg("remembered")])
        assert _texts(await _session(session_factory, team_fixture).get_items()) == ["remembered"]

    async def test_empty_branch_returns_empty_list_not_error(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        assert await _session(session_factory, team_fixture).get_items() == []

    async def test_add_items_with_empty_list_is_a_no_op(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        session = _session(session_factory, team_fixture)
        await session.add_items([])
        assert await session.get_items() == []


class TestPopItem:
    async def test_removes_and_returns_the_most_recent(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        session = _session(session_factory, team_fixture)
        await session.add_items([_msg("kept"), _msg("popped")])
        popped = await session.pop_item()
        assert popped is not None
        assert cast(dict[str, Any], popped)["content"] == "popped"
        assert _texts(await session.get_items()) == ["kept"]

    async def test_returns_none_on_empty_branch(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        assert await _session(session_factory, team_fixture).pop_item() is None

    async def test_pops_only_from_its_own_branch(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        a1 = _session(session_factory, team_fixture, agent_key="agent_a1")
        a2 = _session(session_factory, team_fixture, agent_key="agent_a2")
        await a1.add_items([_msg("a1-item")])
        await a2.add_items([_msg("a2-item")])
        await a2.pop_item()
        assert _texts(await a1.get_items()) == ["a1-item"]
        assert await a2.get_items() == []


class TestBranchIsolation:
    async def test_members_of_one_session_do_not_share_history(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        """A parallel topology runs members concurrently on the same
        input. Merging their turns would hand each of them the others'
        partial reasoning as if it were their own."""
        a1 = _session(session_factory, team_fixture, agent_key="agent_a1")
        a2 = _session(session_factory, team_fixture, agent_key="agent_a2")
        await a1.add_items([_msg("member one thinking")])
        await a2.add_items([_msg("member two thinking")])
        assert _texts(await a1.get_items()) == ["member one thinking"]
        assert _texts(await a2.get_items()) == ["member two thinking"]

    async def test_orchestrator_branch_is_distinct_from_every_member(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        """The null-`agent_id` branch needs `IS NULL`, not `= NULL` —
        getting that wrong matches zero rows and the orchestrator's
        history silently reads as empty."""
        orchestrator = _session(session_factory, team_fixture, agent_key=None)
        member = _session(session_factory, team_fixture, agent_key="agent_a1")
        await orchestrator.add_items([_msg("plan")])
        await member.add_items([_msg("work")])
        assert _texts(await orchestrator.get_items()) == ["plan"]
        assert _texts(await member.get_items()) == ["work"]

    async def test_two_sessions_of_the_same_team_are_separate(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        first = _session(session_factory, team_fixture, session_key="session_a")
        second = _session(session_factory, team_fixture, session_key="session_a2")
        await first.add_items([_msg("run one")])
        assert await second.get_items() == []

    async def test_sdk_session_id_distinguishes_branches(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        a1 = _session(session_factory, team_fixture, agent_key="agent_a1")
        a2 = _session(session_factory, team_fixture, agent_key="agent_a2")
        assert a1.session_id != a2.session_id


class TestTenantIsolation:
    async def test_another_workspace_cannot_read_the_history(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        """Rule 11. The session id alone would already scope this, which
        is exactly why the redundant `workspace_id` predicate has to be
        asserted — otherwise nothing would catch its removal."""
        await _session(session_factory, team_fixture).add_items([_msg("tenant a secret")])
        intruder = PostgresTeamSession(
            team_session_id=team_fixture["session_a"],
            workspace_id=team_fixture["ws_b"],
            agent_id=team_fixture["agent_a1"],
            session_factory=session_factory,
        )
        assert await intruder.get_items() == []
        assert await intruder.pop_item() is None

    async def test_clear_does_not_reach_another_workspace(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        victim = _session(session_factory, team_fixture)
        await victim.add_items([_msg("still here")])
        intruder = PostgresTeamSession(
            team_session_id=team_fixture["session_a"],
            workspace_id=team_fixture["ws_b"],
            agent_id=team_fixture["agent_a1"],
            session_factory=session_factory,
        )
        await intruder.clear_session()
        assert _texts(await victim.get_items()) == ["still here"]


class TestClearSession:
    async def test_clears_only_its_own_branch(
        self, session_factory: async_sessionmaker[AsyncSession], team_fixture: dict[str, str]
    ) -> None:
        a1 = _session(session_factory, team_fixture, agent_key="agent_a1")
        a2 = _session(session_factory, team_fixture, agent_key="agent_a2")
        await a1.add_items([_msg("gone")])
        await a2.add_items([_msg("kept")])
        await a1.clear_session()
        assert await a1.get_items() == []
        assert _texts(await a2.get_items()) == ["kept"]
