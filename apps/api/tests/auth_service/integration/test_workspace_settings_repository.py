"""Real-Postgres tests for `SqlWorkspaceSettingsRepository.upsert` — the
`ON CONFLICT` upsert is exactly the kind of SQL a fake would let pass
while broken (CLAUDE.md §11).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.infrastructure.models import User
from agentverse_api.auth_service.infrastructure.repositories import (
    SqlWorkspaceRepository,
    SqlWorkspaceSettingsRepository,
)

pytestmark = pytest.mark.integration


async def _make_workspace(session: AsyncSession, name: str) -> tuple[str, str]:
    owner_id = f"owner-{name}"
    session.add(
        User(
            id=owner_id,
            name=owner_id,
            email=f"{name}@example.com",
            email_verified=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    await session.flush()
    workspace = await SqlWorkspaceRepository(session).create_workspace(
        name=name, slug=name, owner_user_id=owner_id
    )
    await session.flush()
    return workspace.id, owner_id


async def test_get_returns_none_for_a_workspace_with_no_settings_row(
    db_session: AsyncSession, unique_name: str
) -> None:
    repo = SqlWorkspaceSettingsRepository(db_session)
    workspace_id, _ = await _make_workspace(db_session, unique_name)
    await db_session.commit()

    result = await repo.get(workspace_id)

    assert result is None


async def test_upsert_creates_then_a_second_call_updates_the_same_row(
    db_session: AsyncSession, unique_name: str
) -> None:
    repo = SqlWorkspaceSettingsRepository(db_session)
    workspace_id, owner_id = await _make_workspace(db_session, unique_name)
    await db_session.commit()

    first = await repo.upsert(
        workspace_id=workspace_id,
        logo_url="https://example.com/a.png",
        brand_color="#000000",
        custom_domain=None,
        retention_days=30,
        storage_limit_mb=None,
        updated_by_user_id=owner_id,
    )
    await db_session.commit()
    assert first.retention_days == 30

    second = await repo.upsert(
        workspace_id=workspace_id,
        logo_url="https://example.com/b.png",
        brand_color="#ffffff",
        custom_domain=None,
        retention_days=90,
        storage_limit_mb=2048,
        updated_by_user_id=owner_id,
    )
    await db_session.commit()

    assert second.retention_days == 90
    assert second.logo_url == "https://example.com/b.png"

    fetched = await repo.get(workspace_id)
    assert fetched is not None
    assert fetched.retention_days == 90
    # Exactly one row for the workspace — the second call updated, it
    # did not insert a duplicate (which the 1:1 PK/FK would reject
    # anyway, but this proves the upsert path, not just the constraint).
    assert fetched.storage_limit_mb == 2048
