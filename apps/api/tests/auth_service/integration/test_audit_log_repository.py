"""Real-Postgres tests for `SqlAuditLogRepository.list_for_workspace` —
the cursor-pagination/filter SQL is exactly the kind of thing a fake
would let pass while broken (CLAUDE.md §11).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.infrastructure.models import User
from agentverse_api.auth_service.infrastructure.repositories import (
    SqlAuditLogRepository,
    SqlWorkspaceRepository,
)

pytestmark = pytest.mark.integration


async def _make_user(session: AsyncSession, name: str) -> str:
    """A real `users` row — `audit_logs.actor_user_id` has a real FK to
    it, so a made-up id would fail with an IntegrityError, not a logic
    bug the test would otherwise catch.
    """
    user_id = f"user-{name}"
    session.add(
        User(
            id=user_id,
            name=user_id,
            email=f"{name}@example.com",
            email_verified=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return user_id


async def _make_workspace(session: AsyncSession, name: str) -> str:
    """A real `workspaces` row — `audit_logs.workspace_id` has the same
    FK requirement as `actor_user_id` above.
    """
    owner_id = await _make_user(session, f"owner-{name}")
    workspace = await SqlWorkspaceRepository(session).create_workspace(
        name=name, slug=name, owner_user_id=owner_id
    )
    await session.flush()
    return workspace.id


async def test_list_for_workspace_orders_newest_first_and_filters_by_workspace(
    db_session: AsyncSession, unique_name: str
) -> None:
    repo = SqlAuditLogRepository(db_session)
    ws_a = await _make_workspace(db_session, f"ws-a-{unique_name}")
    ws_b = await _make_workspace(db_session, f"ws-b-{unique_name}")
    actor = await _make_user(db_session, f"actor-{unique_name}")

    for i in range(3):
        await repo.record(
            workspace_id=ws_a,
            actor_user_id=actor,
            action=f"event.{i}",
            target=None,
            outcome="success",
            metadata={},
        )
        # Real Postgres timestamps have enough resolution that a tiny
        # sleep isn't needed in practice, but a tight loop with no I/O
        # between inserts is exactly where two rows could land in the
        # same microsecond — guard the ordering assertion below against
        # that flake deterministically rather than hoping.
        await asyncio.sleep(0.001)
    await repo.record(
        workspace_id=ws_b,
        actor_user_id=actor,
        action="event.other-workspace",
        target=None,
        outcome="success",
        metadata={},
    )
    await db_session.commit()

    page = await repo.list_for_workspace(
        workspace_id=ws_a,
        limit=10,
        cursor=None,
        action=None,
        actor_user_id=None,
        since=None,
        until=None,
    )

    assert [entry.action for entry in page] == ["event.2", "event.1", "event.0"]
    assert all(entry.workspace_id == ws_a for entry in page)


async def test_list_for_workspace_cursor_pagination_covers_every_row_once(
    db_session: AsyncSession, unique_name: str
) -> None:
    repo = SqlAuditLogRepository(db_session)
    workspace_id = await _make_workspace(db_session, unique_name)
    actor = await _make_user(db_session, unique_name)

    for i in range(5):
        await repo.record(
            workspace_id=workspace_id,
            actor_user_id=actor,
            action=f"event.{i}",
            target=None,
            outcome="success",
            metadata={},
        )
        await asyncio.sleep(0.001)
    await db_session.commit()

    first_page = await repo.list_for_workspace(
        workspace_id=workspace_id,
        limit=2,
        cursor=None,
        action=None,
        actor_user_id=None,
        since=None,
        until=None,
    )
    assert [entry.action for entry in first_page] == ["event.4", "event.3"]

    second_page = await repo.list_for_workspace(
        workspace_id=workspace_id,
        limit=2,
        cursor=first_page[-1].created_at.isoformat(),
        action=None,
        actor_user_id=None,
        since=None,
        until=None,
    )
    assert [entry.action for entry in second_page] == ["event.2", "event.1"]

    # No overlap between pages, and the cursor never re-serves the
    # boundary row itself.
    assert {e.id for e in first_page}.isdisjoint({e.id for e in second_page})


async def test_list_for_workspace_filters_by_action_and_actor(
    db_session: AsyncSession, unique_name: str
) -> None:
    repo = SqlAuditLogRepository(db_session)
    workspace_id = await _make_workspace(db_session, unique_name)
    actor_1 = await _make_user(db_session, f"actor1-{unique_name}")
    actor_2 = await _make_user(db_session, f"actor2-{unique_name}")

    await repo.record(
        workspace_id=workspace_id,
        actor_user_id=actor_1,
        action="permission.denied",
        target=None,
        outcome="denied",
        metadata={},
    )
    await repo.record(
        workspace_id=workspace_id,
        actor_user_id=actor_2,
        action="permission.denied",
        target=None,
        outcome="denied",
        metadata={},
    )
    await repo.record(
        workspace_id=workspace_id,
        actor_user_id=actor_1,
        action="workspace.created",
        target=None,
        outcome="success",
        metadata={},
    )
    await db_session.commit()

    by_action = await repo.list_for_workspace(
        workspace_id=workspace_id,
        limit=10,
        cursor=None,
        action="permission.denied",
        actor_user_id=None,
        since=None,
        until=None,
    )
    assert {entry.actor_user_id for entry in by_action} == {actor_1, actor_2}

    by_actor = await repo.list_for_workspace(
        workspace_id=workspace_id,
        limit=10,
        cursor=None,
        action=None,
        actor_user_id=actor_2,
        since=None,
        until=None,
    )
    assert len(by_actor) == 1
    assert by_actor[0].action == "permission.denied"
