"""Real-Postgres tests for `SqlOrganizationSettingsRepository` — the
`ON CONFLICT` upsert and the CASCADE from `organizations` are exactly
the SQL a fake repository would let pass while broken (CLAUDE.md §11).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.infrastructure.models import OrganizationSettings, User
from agentverse_api.auth_service.infrastructure.repositories import (
    SqlOrganizationRepository,
    SqlOrganizationSettingsRepository,
)

pytestmark = pytest.mark.integration


async def _make_organization(session: AsyncSession, name: str) -> tuple[str, str]:
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
    organization = await SqlOrganizationRepository(session).create_organization(
        name=name, slug=name, owner_user_id=owner_id
    )
    await session.flush()
    return organization.id, owner_id


async def test_get_returns_none_for_an_organization_with_no_settings_row(
    db_session: AsyncSession, unique_name: str
) -> None:
    repo = SqlOrganizationSettingsRepository(db_session)
    organization_id, _ = await _make_organization(db_session, unique_name)
    await db_session.commit()

    assert await repo.get(organization_id) is None


async def test_upsert_creates_then_a_second_call_updates_the_same_row(
    db_session: AsyncSession, unique_name: str
) -> None:
    repo = SqlOrganizationSettingsRepository(db_session)
    organization_id, owner_id = await _make_organization(db_session, unique_name)
    await db_session.commit()

    first = await repo.upsert(
        organization_id=organization_id,
        logo_url="https://example.com/a.png",
        brand_color="#000000",
        custom_domain=None,
        website_url=None,
        support_email=None,
        description="First",
        updated_by_user_id=owner_id,
    )
    await db_session.commit()
    assert first.description == "First"

    second = await repo.upsert(
        organization_id=organization_id,
        logo_url="https://example.com/b.png",
        brand_color="#ffffff",
        custom_domain=f"{unique_name}.example.com",
        website_url="https://example.com",
        support_email="help@example.com",
        description="Second",
        updated_by_user_id=owner_id,
    )
    await db_session.commit()

    assert second.description == "Second"
    assert second.custom_domain == f"{unique_name}.example.com"

    fetched = await repo.get(organization_id)
    assert fetched is not None
    assert fetched.logo_url == "https://example.com/b.png"
    assert fetched.support_email == "help@example.com"


async def test_deleting_the_organization_removes_its_settings_row(
    db_session: AsyncSession, unique_name: str
) -> None:
    """CASCADE, not a dangling row. Proven against the real FK rather
    than assumed from the model declaration.
    """
    repo = SqlOrganizationSettingsRepository(db_session)
    organization_id, owner_id = await _make_organization(db_session, unique_name)
    await db_session.commit()

    await repo.upsert(
        organization_id=organization_id,
        logo_url=None,
        brand_color=None,
        custom_domain=None,
        website_url=None,
        support_email=None,
        description=None,
        updated_by_user_id=owner_id,
    )
    await db_session.commit()

    await SqlOrganizationRepository(db_session).delete_organization(organization_id)
    await db_session.commit()

    remaining = await db_session.execute(
        select(OrganizationSettings).where(OrganizationSettings.organization_id == organization_id)
    )
    assert remaining.scalar_one_or_none() is None
