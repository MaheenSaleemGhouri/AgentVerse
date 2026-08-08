"""The repository against real Postgres.

Two things are only true in the database and nowhere else: the scoping
`WHERE` clauses that make a session invisible to the wrong tenant or the
wrong colleague, and the `role` CHECK constraint that keeps a bad value
out of a column the domain types as a `Literal`.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.assistant_service.infrastructure.repositories import (
    SqlAssistantSessionRepository,
)

pytestmark = pytest.mark.integration


async def _workspace(session: AsyncSession) -> str:
    workspace_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO workspaces (id, name, slug, created_at) VALUES (:id, :name, :slug, now())"
        ),
        {"id": workspace_id, "name": "Assistant Test", "slug": f"ws-{workspace_id[:8]}"},
    )
    await session.flush()
    return workspace_id


async def _user(session: AsyncSession) -> str:
    user_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO users (id, email, name, email_verified, created_at, updated_at) "
            "VALUES (:id, :email, 'Assistant Tester', true, now(), now())"
        ),
        {"id": user_id, "email": f"assistant-{user_id[:8]}@example.test"},
    )
    await session.flush()
    return user_id


class TestScoping:
    async def test_a_session_is_invisible_to_another_workspace(
        self, db_session: AsyncSession
    ) -> None:
        repo = SqlAssistantSessionRepository(db_session)
        mine = await _workspace(db_session)
        theirs = await _workspace(db_session)
        user_id = await _user(db_session)
        session = await repo.create_session(
            workspace_id=mine, user_id=user_id, title="How do I sign a webhook?"
        )

        assert (
            await repo.get_session(workspace_id=theirs, user_id=user_id, session_id=session.id)
            is None
        )
        await db_session.rollback()

    async def test_a_session_is_invisible_to_a_colleague_in_the_same_workspace(
        self, db_session: AsyncSession
    ) -> None:
        """Workspace scoping alone is not enough here — a help
        conversation is personal, and a workspace admin reading their
        colleagues' half-typed questions is a privacy surprise."""
        repo = SqlAssistantSessionRepository(db_session)
        workspace_id = await _workspace(db_session)
        mine = await _user(db_session)
        theirs = await _user(db_session)
        session = await repo.create_session(workspace_id=workspace_id, user_id=mine, title="Mine")

        assert (
            await repo.get_session(workspace_id=workspace_id, user_id=theirs, session_id=session.id)
            is None
        )
        assert await repo.list_sessions(workspace_id=workspace_id, user_id=theirs, limit=10) == []
        await db_session.rollback()


class TestMessages:
    async def test_messages_come_back_in_the_order_they_were_written(
        self, db_session: AsyncSession
    ) -> None:
        repo = SqlAssistantSessionRepository(db_session)
        workspace_id = await _workspace(db_session)
        user_id = await _user(db_session)
        session = await repo.create_session(workspace_id=workspace_id, user_id=user_id, title="t")

        await repo.append_message(session_id=session.id, role="user", content="first")
        await repo.append_message(session_id=session.id, role="assistant", content="second")
        await repo.append_message(session_id=session.id, role="user", content="third")

        messages = await repo.list_messages(session_id=session.id)

        assert [message.content for message in messages] == ["first", "second", "third"]
        await db_session.rollback()

    async def test_an_unknown_role_is_rejected_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        """The CHECK constraint is the enforcement point the domain's
        `Literal` type relies on — mypy cannot reach a raw INSERT."""
        repo = SqlAssistantSessionRepository(db_session)
        workspace_id = await _workspace(db_session)
        user_id = await _user(db_session)
        session = await repo.create_session(workspace_id=workspace_id, user_id=user_id, title="t")
        await db_session.flush()

        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO assistant_messages (id, session_id, role, content, created_at) "
                    "VALUES (:id, :session_id, 'system', 'x', now())"
                ),
                {"id": str(uuid.uuid4()), "session_id": session.id},
            )
        await db_session.rollback()

    async def test_deleting_a_session_takes_its_messages_with_it(
        self, db_session: AsyncSession
    ) -> None:
        repo = SqlAssistantSessionRepository(db_session)
        workspace_id = await _workspace(db_session)
        user_id = await _user(db_session)
        session = await repo.create_session(workspace_id=workspace_id, user_id=user_id, title="t")
        await repo.append_message(session_id=session.id, role="user", content="q")
        await db_session.flush()

        await db_session.execute(
            text("DELETE FROM assistant_sessions WHERE id = :id"), {"id": session.id}
        )

        remaining = await db_session.scalar(
            text("SELECT count(*) FROM assistant_messages WHERE session_id = :id"),
            {"id": session.id},
        )
        assert remaining == 0
        await db_session.rollback()
