"""Real-Postgres tests for `SqlWorkspaceRepository` — an "integration
test" that mocked the database would give false confidence (CLAUDE.md
§11), so this hits the actual schema Alembic created.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.infrastructure.repositories import SqlWorkspaceRepository

pytestmark = pytest.mark.integration


async def _make_user(session: AsyncSession, user_id: str, email: str) -> None:
    from datetime import UTC, datetime

    from agentverse_api.auth_service.infrastructure.models import User

    session.add(
        User(
            id=user_id,
            name=user_id,
            email=email,
            email_verified=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    await session.flush()


async def test_create_workspace_and_get_membership(
    db_session: AsyncSession, unique_name: str
) -> None:
    await _make_user(db_session, f"user-{unique_name}", f"{unique_name}@example.com")
    repo = SqlWorkspaceRepository(db_session)

    workspace = await repo.create_workspace(
        name=unique_name, slug=unique_name, owner_user_id=f"user-{unique_name}"
    )
    await db_session.commit()

    fetched = await repo.get_workspace(workspace.id)
    assert fetched is not None
    assert fetched.slug == unique_name

    membership = await repo.get_membership(workspace_id=workspace.id, user_id=f"user-{unique_name}")
    assert membership is not None
    assert membership.role is Role.OWNER


async def test_list_for_user_returns_only_their_workspaces(
    db_session: AsyncSession, unique_name: str
) -> None:
    user_a = f"user-a-{unique_name}"
    user_b = f"user-b-{unique_name}"
    await _make_user(db_session, user_a, f"a-{unique_name}@example.com")
    await _make_user(db_session, user_b, f"b-{unique_name}@example.com")
    repo = SqlWorkspaceRepository(db_session)

    workspace_a = await repo.create_workspace(
        name=f"ws-a-{unique_name}", slug=f"ws-a-{unique_name}", owner_user_id=user_a
    )
    await repo.create_workspace(
        name=f"ws-b-{unique_name}", slug=f"ws-b-{unique_name}", owner_user_id=user_b
    )
    await db_session.commit()

    summaries = await repo.list_for_user(user_a)

    assert [s.workspace.id for s in summaries] == [workspace_a.id]


async def test_count_owners_reflects_role_changes(
    db_session: AsyncSession, unique_name: str
) -> None:
    owner_id = f"owner-{unique_name}"
    member_id = f"member-{unique_name}"
    await _make_user(db_session, owner_id, f"owner-{unique_name}@example.com")
    await _make_user(db_session, member_id, f"member-{unique_name}@example.com")
    repo = SqlWorkspaceRepository(db_session)

    workspace = await repo.create_workspace(
        name=unique_name, slug=unique_name, owner_user_id=owner_id
    )
    await repo.add_member(workspace_id=workspace.id, user_id=member_id, role=Role.OWNER)
    await db_session.commit()

    assert await repo.count_owners(workspace.id) == 2

    await repo.update_member_role(workspace_id=workspace.id, user_id=member_id, role=Role.ADMIN)
    await db_session.commit()

    assert await repo.count_owners(workspace.id) == 1
