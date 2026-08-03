"""Real-Postgres tests for `SqlOrganizationRepository` — the FK/cascade
behavior (`ON DELETE SET NULL` on `workspaces.organization_id`, `ON
DELETE CASCADE` on `organization_members`) is exactly the kind of
behavior a fake would let pass while broken (CLAUDE.md §11).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.infrastructure.models import User
from agentverse_api.auth_service.infrastructure.repositories import (
    SqlOrganizationRepository,
    SqlWorkspaceRepository,
)

pytestmark = pytest.mark.integration


async def _make_user(session: AsyncSession, user_id: str) -> None:
    session.add(
        User(
            id=user_id,
            name=user_id,
            email=f"{user_id}@example.com",
            email_verified=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    await session.flush()


async def test_deleting_an_organization_detaches_its_workspaces_not_deletes_them(
    db_session: AsyncSession, unique_name: str
) -> None:
    owner_id = f"owner-{unique_name}"
    await _make_user(db_session, owner_id)

    org_repo = SqlOrganizationRepository(db_session)
    workspace_repo = SqlWorkspaceRepository(db_session)

    organization = await org_repo.create_organization(
        name=f"org-{unique_name}", slug=f"org-{unique_name}", owner_user_id=owner_id
    )
    workspace = await workspace_repo.create_workspace(
        name=f"ws-{unique_name}", slug=f"ws-{unique_name}", owner_user_id=owner_id
    )
    await org_repo.attach_workspace(organization_id=organization.id, workspace_id=workspace.id)
    await db_session.commit()

    fetched = await workspace_repo.get_workspace(workspace.id)
    assert fetched is not None
    assert fetched.organization_id == organization.id

    await org_repo.delete_organization(organization.id)
    await db_session.commit()

    # The workspace survives — only detached. Its own RBAC (`workspace_members`,
    # via `create_workspace`'s owner row) is completely untouched by this.
    surviving = await workspace_repo.get_workspace(workspace.id)
    assert surviving is not None
    assert surviving.organization_id is None
    membership = await workspace_repo.get_membership(workspace_id=workspace.id, user_id=owner_id)
    assert membership is not None
    assert membership.role is Role.OWNER


async def test_deleting_an_organization_cascades_its_membership_rows(
    db_session: AsyncSession, unique_name: str
) -> None:
    owner_id = f"owner2-{unique_name}"
    member_id = f"member2-{unique_name}"
    await _make_user(db_session, owner_id)
    await _make_user(db_session, member_id)

    org_repo = SqlOrganizationRepository(db_session)
    organization = await org_repo.create_organization(
        name=f"org2-{unique_name}", slug=f"org2-{unique_name}", owner_user_id=owner_id
    )
    await org_repo.add_member(organization_id=organization.id, user_id=member_id, role=Role.MEMBER)
    await db_session.commit()

    await org_repo.delete_organization(organization.id)
    await db_session.commit()

    assert await org_repo.get_organization(organization.id) is None
    assert await org_repo.get_membership(organization_id=organization.id, user_id=owner_id) is None


async def test_attaching_a_workspace_never_creates_a_workspace_members_row(
    db_session: AsyncSession, unique_name: str
) -> None:
    """The ADR-0011 invariant at the repository layer: attach touches only
    `workspaces.organization_id`, never `workspace_members`."""
    org_owner = f"org-owner-{unique_name}"
    workspace_owner = f"ws-owner-{unique_name}"
    await _make_user(db_session, org_owner)
    await _make_user(db_session, workspace_owner)

    org_repo = SqlOrganizationRepository(db_session)
    workspace_repo = SqlWorkspaceRepository(db_session)

    organization = await org_repo.create_organization(
        name=f"org3-{unique_name}", slug=f"org3-{unique_name}", owner_user_id=org_owner
    )
    workspace = await workspace_repo.create_workspace(
        name=f"ws3-{unique_name}", slug=f"ws3-{unique_name}", owner_user_id=workspace_owner
    )
    await org_repo.attach_workspace(organization_id=organization.id, workspace_id=workspace.id)
    await db_session.commit()

    # The org owner has no workspace membership at all — attaching granted
    # them nothing.
    membership = await workspace_repo.get_membership(workspace_id=workspace.id, user_id=org_owner)
    assert membership is None
