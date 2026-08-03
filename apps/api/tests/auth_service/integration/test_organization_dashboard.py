"""Real-Postgres tests for the organization dashboard's presence join.

The fake repository reports "never signed in" for everyone, which is the
honest in-memory answer but tests nothing — the session aggregation is
multi-join SQL, and this is the only place it can actually be wrong.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.infrastructure.models import Session, User
from agentverse_api.auth_service.infrastructure.repositories import (
    SqlOrganizationRepository,
    SqlWorkspaceRepository,
)

pytestmark = pytest.mark.integration


async def _make_user(session: AsyncSession, name: str) -> str:
    user_id = f"user-{name}"
    session.add(
        User(
            id=user_id,
            name=name,
            email=f"{name}@example.com",
            email_verified=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return user_id


def _session_row(*, user_id: str, created_at: datetime, expires_at: datetime, ua: str) -> Session:
    return Session(
        id=f"sess-{user_id}-{created_at.timestamp()}",
        user_id=user_id,
        token=f"token-{user_id}-{created_at.timestamp()}",
        expires_at=expires_at,
        ip_address="203.0.113.10",
        user_agent=ua,
        created_at=created_at,
        updated_at=created_at,
    )


async def test_presence_reports_the_most_recent_session_not_an_arbitrary_one(
    db_session: AsyncSession, unique_name: str
) -> None:
    owner = await _make_user(db_session, unique_name)
    organization = await SqlOrganizationRepository(db_session).create_organization(
        name=unique_name, slug=unique_name, owner_user_id=owner
    )
    now = datetime.now(UTC)
    db_session.add(
        _session_row(
            user_id=owner,
            created_at=now - timedelta(days=5),
            expires_at=now - timedelta(days=4),
            ua="OldBrowser/1.0",
        )
    )
    db_session.add(
        _session_row(
            user_id=owner,
            created_at=now - timedelta(hours=1),
            expires_at=now + timedelta(days=1),
            ua="NewBrowser/2.0",
        )
    )
    await db_session.commit()

    presence = await SqlOrganizationRepository(db_session).list_member_presence(organization.id)

    assert len(presence) == 1
    entry = presence[0]
    assert entry.last_user_agent == "NewBrowser/2.0"
    assert entry.has_active_session is True
    assert entry.last_login_at is not None


async def test_a_member_with_only_expired_sessions_is_not_reported_active(
    db_session: AsyncSession, unique_name: str
) -> None:
    """`has_active_session` claims exactly one thing — an unexpired
    session exists. An expired one must not satisfy it.
    """
    owner = await _make_user(db_session, unique_name)
    organization = await SqlOrganizationRepository(db_session).create_organization(
        name=unique_name, slug=unique_name, owner_user_id=owner
    )
    now = datetime.now(UTC)
    db_session.add(
        _session_row(
            user_id=owner,
            created_at=now - timedelta(days=30),
            expires_at=now - timedelta(days=29),
            ua="Expired/1.0",
        )
    )
    await db_session.commit()

    entry = (await SqlOrganizationRepository(db_session).list_member_presence(organization.id))[0]

    assert entry.has_active_session is False
    # Still reports when they were last seen — "not active" is not the
    # same as "no history", and conflating them loses real information.
    assert entry.last_login_at is not None


async def test_a_member_who_never_signed_in_appears_with_no_session_data(
    db_session: AsyncSession, unique_name: str
) -> None:
    """The join is an outer join — a member with no sessions must still
    appear in the list, not silently vanish from the dashboard.
    """
    owner = await _make_user(db_session, unique_name)
    never = await _make_user(db_session, f"{unique_name}-never")
    repo = SqlOrganizationRepository(db_session)
    organization = await repo.create_organization(
        name=unique_name, slug=unique_name, owner_user_id=owner
    )
    await repo.add_member(organization_id=organization.id, user_id=never, role=Role.MEMBER)
    await db_session.commit()

    presence = await repo.list_member_presence(organization.id)
    entry = next(p for p in presence if p.user_id == never)

    assert len(presence) == 2
    assert entry.last_login_at is None
    assert entry.has_active_session is False
    assert entry.role is Role.MEMBER


async def test_stats_count_workspaces_members_and_roles(
    db_session: AsyncSession, unique_name: str
) -> None:
    owner = await _make_user(db_session, unique_name)
    analyst = await _make_user(db_session, f"{unique_name}-analyst")
    repo = SqlOrganizationRepository(db_session)
    organization = await repo.create_organization(
        name=unique_name, slug=unique_name, owner_user_id=owner
    )
    await repo.add_member(organization_id=organization.id, user_id=analyst, role=Role.ANALYST)

    workspace = await SqlWorkspaceRepository(db_session).create_workspace(
        name=unique_name, slug=unique_name, owner_user_id=owner
    )
    await repo.attach_workspace(organization_id=organization.id, workspace_id=workspace.id)
    await db_session.commit()

    stats = await repo.stats(organization.id)

    assert stats.workspace_count == 1
    assert stats.member_count == 2
    assert stats.active_member_count == 2
    assert stats.suspended_member_count == 0
    assert stats.members_by_role == {Role.OWNER: 1, Role.ANALYST: 1}


async def test_a_suspended_member_is_counted_separately_not_dropped(
    db_session: AsyncSession, unique_name: str
) -> None:
    """A suspended member still occupies a seat and still needs to be
    visible — counting them as gone would hide them from the admin who
    needs to act on them.
    """
    owner = await _make_user(db_session, unique_name)
    suspended = await _make_user(db_session, f"{unique_name}-susp")
    repo = SqlOrganizationRepository(db_session)
    organization = await repo.create_organization(
        name=unique_name, slug=unique_name, owner_user_id=owner
    )
    await repo.add_member(organization_id=organization.id, user_id=suspended, role=Role.MEMBER)
    await repo.suspend_member(organization_id=organization.id, user_id=suspended)
    await db_session.commit()

    stats = await repo.stats(organization.id)
    presence = await repo.list_member_presence(organization.id)

    assert stats.member_count == 2
    assert stats.active_member_count == 1
    assert stats.suspended_member_count == 1
    assert any(entry.suspended_at is not None for entry in presence)
