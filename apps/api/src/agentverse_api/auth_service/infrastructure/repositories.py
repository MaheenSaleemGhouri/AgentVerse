"""Postgres implementations of `domain/ports.py`'s repository protocols."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.domain.entities import (
    ApiKey as ApiKeyEntity,
)
from agentverse_api.auth_service.domain.entities import (
    AuditLogEntry,
    WorkspaceSummary,
)
from agentverse_api.auth_service.domain.entities import (
    Workspace as WorkspaceEntity,
)
from agentverse_api.auth_service.domain.entities import (
    WorkspaceMember as WorkspaceMemberEntity,
)
from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.infrastructure.models import (
    ApiKey,
    AuditLog,
    Workspace,
    WorkspaceMember,
)


def _to_workspace(row: Workspace) -> WorkspaceEntity:
    return WorkspaceEntity(id=row.id, name=row.name, slug=row.slug, created_at=row.created_at)


def _to_member(row: WorkspaceMember) -> WorkspaceMemberEntity:
    return WorkspaceMemberEntity(
        workspace_id=row.workspace_id,
        user_id=row.user_id,
        role=row.role,
        created_at=row.created_at,
    )


def _to_api_key(row: ApiKey) -> ApiKeyEntity:
    return ApiKeyEntity(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        key_prefix=row.key_prefix,
        hashed_key=row.hashed_key,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
    )


def _to_audit_entry(row: AuditLog) -> AuditLogEntry:
    return AuditLogEntry(
        id=row.id,
        workspace_id=row.workspace_id,
        actor_user_id=row.actor_user_id,
        action=row.action,
        target=row.target,
        outcome=row.outcome,
        metadata=row.log_metadata,
        created_at=row.created_at,
    )


class SqlWorkspaceRepository:
    """Implements `domain.ports.WorkspaceRepository` against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_workspace(
        self, *, name: str, slug: str, owner_user_id: str
    ) -> WorkspaceEntity:
        now = datetime.now(UTC)
        row = Workspace(name=name, slug=slug, created_at=now)
        self._session.add(row)
        await self._session.flush()

        member = WorkspaceMember(
            workspace_id=row.id, user_id=owner_user_id, role=Role.OWNER, created_at=now
        )
        self._session.add(member)
        await self._session.flush()
        return _to_workspace(row)

    async def get_workspace(self, workspace_id: str) -> WorkspaceEntity | None:
        row = await self._session.get(Workspace, workspace_id)
        return _to_workspace(row) if row is not None else None

    async def list_for_user(self, user_id: str) -> list[WorkspaceSummary]:
        stmt = (
            select(Workspace, WorkspaceMember.role)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user_id)
            .order_by(Workspace.created_at)
        )
        result = await self._session.execute(stmt)
        return [
            WorkspaceSummary(workspace=_to_workspace(workspace_row), role=role)
            for workspace_row, role in result.all()
        ]

    async def slug_exists(self, slug: str) -> bool:
        stmt = select(Workspace.id).where(Workspace.slug == slug)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_membership(
        self, *, workspace_id: str, user_id: str
    ) -> WorkspaceMemberEntity | None:
        stmt = select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _to_member(row) if row is not None else None

    async def add_member(
        self, *, workspace_id: str, user_id: str, role: Role
    ) -> WorkspaceMemberEntity:
        row = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=role, created_at=datetime.now(UTC)
        )
        self._session.add(row)
        await self._session.flush()
        return _to_member(row)

    async def update_member_role(
        self, *, workspace_id: str, user_id: str, role: Role
    ) -> WorkspaceMemberEntity:
        stmt = select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one()
        row.role = role
        await self._session.flush()
        return _to_member(row)

    async def remove_member(self, *, workspace_id: str, user_id: str) -> None:
        stmt = select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one()
        await self._session.delete(row)
        await self._session.flush()

    async def count_owners(self, workspace_id: str) -> int:
        stmt = select(func.count()).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == Role.OWNER,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_members(self, workspace_id: str) -> list[WorkspaceMemberEntity]:
        stmt = select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
        result = await self._session.execute(stmt)
        return [_to_member(row) for row in result.scalars().all()]


class SqlApiKeyRepository:
    """Implements `domain.ports.ApiKeyRepository` against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_api_key(
        self,
        *,
        workspace_id: str,
        name: str,
        key_prefix: str,
        hashed_key: str,
        created_by_user_id: str,
    ) -> ApiKeyEntity:
        row = ApiKey(
            workspace_id=workspace_id,
            name=name,
            key_prefix=key_prefix,
            hashed_key=hashed_key,
            created_by_user_id=created_by_user_id,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return _to_api_key(row)

    async def list_api_keys(self, workspace_id: str) -> list[ApiKeyEntity]:
        stmt = select(ApiKey).where(ApiKey.workspace_id == workspace_id)
        result = await self._session.execute(stmt)
        return [_to_api_key(row) for row in result.scalars().all()]

    async def get_api_key(self, api_key_id: str) -> ApiKeyEntity | None:
        row = await self._session.get(ApiKey, api_key_id)
        return _to_api_key(row) if row is not None else None

    async def revoke_api_key(self, api_key_id: str) -> None:
        row = await self._session.get(ApiKey, api_key_id)
        if row is not None:
            row.revoked_at = datetime.now(UTC)
            await self._session.flush()


class SqlAuditLogRepository:
    """Implements `domain.ports.AuditLogRepository` against Postgres.

    `audit_logs` is append-only (CLAUDE.md §8) — this repository exposes
    no update/delete method, by construction, not just by DB grant.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        workspace_id: str | None,
        actor_user_id: str | None,
        action: str,
        target: str | None,
        outcome: str,
        metadata: dict[str, str],
    ) -> AuditLogEntry:
        row = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            target=target,
            outcome=outcome,
            log_metadata=metadata,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return _to_audit_entry(row)
