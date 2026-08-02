"""Real-Postgres tests for `SqlInvitationRepository` — the identifier
packing/parsing round-trip and single-use `consumed_at` enforcement are
exactly the kind of thing a fake would let pass while broken (CLAUDE.md
§11).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.domain.invitation_target_type import InvitationTargetType
from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.infrastructure.repositories import SqlInvitationRepository

pytestmark = pytest.mark.integration


async def test_create_then_get_by_token_round_trips_every_field(
    db_session: AsyncSession, unique_name: str
) -> None:
    repo = SqlInvitationRepository(db_session)
    expires_at = datetime.now(UTC) + timedelta(days=7)

    created = await repo.create(
        target_type=InvitationTargetType.ORGANIZATION,
        target_id=f"org-{unique_name}",
        role=Role.ADMIN,
        inviter_user_id=f"inviter-{unique_name}",
        email=f"{unique_name}@example.com",
        token=f"token-{unique_name}",
        expires_at=expires_at,
    )
    await db_session.commit()

    fetched = await repo.get_by_token(f"token-{unique_name}")

    assert fetched is not None
    assert fetched.target_type is InvitationTargetType.ORGANIZATION
    assert fetched.target_id == f"org-{unique_name}"
    assert fetched.role is Role.ADMIN
    assert fetched.inviter_user_id == f"inviter-{unique_name}"
    assert fetched.email == f"{unique_name}@example.com"
    assert fetched.consumed_at is None
    assert created.token == fetched.token


async def test_get_by_token_returns_none_for_an_unknown_token(
    db_session: AsyncSession, unique_name: str
) -> None:
    repo = SqlInvitationRepository(db_session)

    assert await repo.get_by_token(f"nope-{unique_name}") is None


async def test_consume_marks_the_row_consumed_and_is_reflected_on_the_next_read(
    db_session: AsyncSession, unique_name: str
) -> None:
    repo = SqlInvitationRepository(db_session)
    token = f"token2-{unique_name}"
    await repo.create(
        target_type=InvitationTargetType.WORKSPACE,
        target_id=f"ws-{unique_name}",
        role=Role.MEMBER,
        inviter_user_id=f"inviter2-{unique_name}",
        email=f"{unique_name}-2@example.com",
        token=token,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    await db_session.commit()

    await repo.consume(token)
    await db_session.commit()

    fetched = await repo.get_by_token(token)
    assert fetched is not None
    assert fetched.consumed_at is not None
