"""Postgres implementations of `domain/ports.py`'s repository protocols."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, update
from sqlalchemy import or_ as sa_or
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.domain.api_key_scope import ApiKeyScope
from agentverse_api.auth_service.domain.entities import (
    ApiKey as ApiKeyEntity,
)
from agentverse_api.auth_service.domain.entities import (
    AuditLogEntry,
    Invitation,
    IpAllowlistEntry,
    MemberPresence,
    OrganizationStats,
    OrganizationSummary,
    ScimUser,
    UserSummary,
    WorkspaceSummary,
)
from agentverse_api.auth_service.domain.entities import (
    CustomRole as CustomRoleEntity,
)
from agentverse_api.auth_service.domain.entities import (
    Organization as OrganizationEntity,
)
from agentverse_api.auth_service.domain.entities import (
    OrganizationMember as OrganizationMemberEntity,
)
from agentverse_api.auth_service.domain.entities import (
    OrganizationSettings as OrganizationSettingsEntity,
)
from agentverse_api.auth_service.domain.entities import (
    ResourcePermission as ResourcePermissionEntity,
)
from agentverse_api.auth_service.domain.entities import (
    ScimToken as ScimTokenEntity,
)
from agentverse_api.auth_service.domain.entities import (
    SecurityEvent as SecurityEventEntity,
)
from agentverse_api.auth_service.domain.entities import (
    SsoConfiguration as SsoConfigurationEntity,
)
from agentverse_api.auth_service.domain.entities import (
    TrustedDevice as TrustedDeviceEntity,
)
from agentverse_api.auth_service.domain.entities import (
    Workspace as WorkspaceEntity,
)
from agentverse_api.auth_service.domain.entities import (
    WorkspaceMember as WorkspaceMemberEntity,
)
from agentverse_api.auth_service.domain.entities import (
    WorkspaceSettings as WorkspaceSettingsEntity,
)
from agentverse_api.auth_service.domain.exceptions import CustomRoleNotFoundError
from agentverse_api.auth_service.domain.invitation_target_type import InvitationTargetType
from agentverse_api.auth_service.domain.permission import Permission
from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.domain.security import (
    PasswordPolicy as PasswordPolicyEntity,
)
from agentverse_api.auth_service.domain.security import (
    SecurityEventType,
    SecuritySeverity,
    severity_for,
)
from agentverse_api.auth_service.domain.sso import SsoPreset, SsoProtocol
from agentverse_api.auth_service.infrastructure.models import (
    ApiKey,
    AuditLog,
    Organization,
    OrganizationMember,
    OrganizationSettings,
    PasswordPolicy,
    ResourcePermission,
    ScimToken,
    SecurityEvent,
    Session,
    SsoConfiguration,
    TrustedDevice,
    User,
    Verification,
    Workspace,
    WorkspaceIpAllowlist,
    WorkspaceMember,
    WorkspaceSettings,
)
from agentverse_api.auth_service.infrastructure.models import (
    CustomRole as CustomRoleModel,
)
from agentverse_api.auth_service.infrastructure.models import (
    CustomRolePermission as CustomRolePermissionModel,
)

_WORKSPACE_INVITE_PREFIX = "workspace-invite"
_ORGANIZATION_INVITE_PREFIX = "organization-invite"
_INVITE_PREFIX_BY_TARGET_TYPE = {
    InvitationTargetType.WORKSPACE: _WORKSPACE_INVITE_PREFIX,
    InvitationTargetType.ORGANIZATION: _ORGANIZATION_INVITE_PREFIX,
}
_TARGET_TYPE_BY_INVITE_PREFIX = {v: k for k, v in _INVITE_PREFIX_BY_TARGET_TYPE.items()}


def _build_invitation_identifier(
    *,
    target_type: InvitationTargetType,
    target_id: str,
    role: Role,
    inviter_user_id: str,
    email: str,
) -> str:
    # `inviter_user_id` is always a UUID/Better-Auth-generated id (never
    # contains ":", unlike email, which the trailing maxsplit=4 in
    # `_parse_invitation_identifier` protects against regardless).
    prefix = _INVITE_PREFIX_BY_TARGET_TYPE[target_type]
    return f"{prefix}:{target_id}:{role.value}:{inviter_user_id}:{email}"


def _parse_invitation_identifier(
    identifier: str,
) -> tuple[InvitationTargetType, str, Role, str, str] | None:
    parts = identifier.split(":", 4)
    if len(parts) != 5:
        return None
    prefix, target_id, role_str, inviter_user_id, email = parts
    target_type = _TARGET_TYPE_BY_INVITE_PREFIX.get(prefix)
    if target_type is None:
        return None
    try:
        role = Role(role_str)
    except ValueError:
        return None
    return target_type, target_id, role, inviter_user_id, email


def _to_invitation(row: Verification) -> Invitation | None:
    parsed = _parse_invitation_identifier(row.identifier)
    if parsed is None:
        # Not an invitation row (e.g. a Better Auth reset-password or
        # email-verification row) — the caller treats this the same as
        # "no such invitation" (CLAUDE.md Rule 11: never distinguish
        # "doesn't exist" from "isn't yours to see").
        return None
    target_type, target_id, role, inviter_user_id, email = parsed
    return Invitation(
        target_type=target_type,
        target_id=target_id,
        role=role,
        inviter_user_id=inviter_user_id,
        email=email,
        token=row.value,
        expires_at=row.expires_at,
        consumed_at=row.consumed_at,
        created_at=row.created_at,
    )


def _to_workspace(row: Workspace) -> WorkspaceEntity:
    return WorkspaceEntity(
        id=row.id,
        name=row.name,
        slug=row.slug,
        created_at=row.created_at,
        organization_id=row.organization_id,
    )


def _to_organization(row: Organization) -> OrganizationEntity:
    return OrganizationEntity(id=row.id, name=row.name, slug=row.slug, created_at=row.created_at)


def _to_org_member(row: OrganizationMember) -> OrganizationMemberEntity:
    return OrganizationMemberEntity(
        organization_id=row.organization_id,
        user_id=row.user_id,
        role=row.role,
        created_at=row.created_at,
        suspended_at=row.suspended_at,
    )


def _to_member(row: WorkspaceMember) -> WorkspaceMemberEntity:
    return WorkspaceMemberEntity(
        workspace_id=row.workspace_id,
        user_id=row.user_id,
        role=row.role,
        created_at=row.created_at,
        custom_role_id=row.custom_role_id,
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
        scope=ApiKeyScope(row.scope),
        tier=row.tier,
        rotated_from_id=row.rotated_from_id,
        expires_at=row.expires_at,
        use_count=row.use_count,
    )


def _to_workspace_settings(row: WorkspaceSettings) -> WorkspaceSettingsEntity:
    return WorkspaceSettingsEntity(
        workspace_id=row.workspace_id,
        logo_url=row.logo_url,
        brand_color=row.brand_color,
        custom_domain=row.custom_domain,
        retention_days=row.retention_days,
        storage_limit_mb=row.storage_limit_mb,
        updated_at=row.updated_at,
        updated_by_user_id=row.updated_by_user_id,
    )


def _to_organization_settings(row: OrganizationSettings) -> OrganizationSettingsEntity:
    return OrganizationSettingsEntity(
        organization_id=row.organization_id,
        logo_url=row.logo_url,
        brand_color=row.brand_color,
        custom_domain=row.custom_domain,
        website_url=row.website_url,
        support_email=row.support_email,
        description=row.description,
        updated_at=row.updated_at,
        updated_by_user_id=row.updated_by_user_id,
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
        organization_id=row.organization_id,
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

    async def count_members(self, workspace_id: str) -> int:
        """Seats in use, for plan-limit enforcement.

        Counts every membership row regardless of role: a viewer still
        occupies a seat, and billing a workspace for fewer seats than it
        has members would under-charge exactly the customers who grow.
        """
        stmt = select(func.count()).where(WorkspaceMember.workspace_id == workspace_id)
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def list_members(self, workspace_id: str) -> list[WorkspaceMemberEntity]:
        stmt = select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
        result = await self._session.execute(stmt)
        return [_to_member(row) for row in result.scalars().all()]

    async def count_two_factor_coverage(self, workspace_id: str) -> tuple[int, int]:
        # One query, two aggregates: computing the ratio from two
        # separate round trips could straddle a membership change and
        # report more enabled members than total.
        stmt = (
            select(
                func.count(User.id).filter(User.two_factor_enabled.is_(True)),
                func.count(User.id),
            )
            .select_from(WorkspaceMember)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id)
        )
        enabled, total = (await self._session.execute(stmt)).one()
        return int(enabled), int(total)


class SqlOrganizationRepository:
    """Implements `domain.ports.OrganizationRepository` against Postgres.

    Never touches `workspace_members` or `WorkspaceMember` rows — every
    method here operates on organization membership or the purely
    additive `workspaces.organization_id` link, never on workspace
    authorization itself (ADR-0011).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_organization(
        self, *, name: str, slug: str, owner_user_id: str
    ) -> OrganizationEntity:
        now = datetime.now(UTC)
        row = Organization(name=name, slug=slug, created_at=now)
        self._session.add(row)
        await self._session.flush()

        member = OrganizationMember(
            organization_id=row.id, user_id=owner_user_id, role=Role.OWNER, created_at=now
        )
        self._session.add(member)
        await self._session.flush()
        return _to_organization(row)

    async def get_organization(self, organization_id: str) -> OrganizationEntity | None:
        row = await self._session.get(Organization, organization_id)
        return _to_organization(row) if row is not None else None

    async def list_for_user(self, user_id: str) -> list[OrganizationSummary]:
        stmt = (
            select(Organization, OrganizationMember.role)
            .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
            .where(OrganizationMember.user_id == user_id)
            .order_by(Organization.created_at)
        )
        result = await self._session.execute(stmt)
        return [
            OrganizationSummary(organization=_to_organization(org_row), role=role)
            for org_row, role in result.all()
        ]

    async def slug_exists(self, slug: str) -> bool:
        stmt = select(Organization.id).where(Organization.slug == slug)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def rename_organization(self, *, organization_id: str, name: str) -> OrganizationEntity:
        row = await self._session.get(Organization, organization_id)
        assert row is not None
        row.name = name
        await self._session.flush()
        return _to_organization(row)

    async def delete_organization(self, organization_id: str) -> None:
        row = await self._session.get(Organization, organization_id)
        if row is not None:
            # `organization_members` cascades; `workspaces.organization_id`
            # is `ON DELETE SET NULL` — both enforced at the DB level by
            # the migration's FK definitions, not by application code.
            await self._session.delete(row)
            await self._session.flush()

    async def get_membership(
        self, *, organization_id: str, user_id: str
    ) -> OrganizationMemberEntity | None:
        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _to_org_member(row) if row is not None else None

    async def add_member(
        self, *, organization_id: str, user_id: str, role: Role
    ) -> OrganizationMemberEntity:
        row = OrganizationMember(
            organization_id=organization_id,
            user_id=user_id,
            role=role,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return _to_org_member(row)

    async def update_member_role(
        self, *, organization_id: str, user_id: str, role: Role
    ) -> OrganizationMemberEntity:
        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one()
        row.role = role
        await self._session.flush()
        return _to_org_member(row)

    async def suspend_member(
        self, *, organization_id: str, user_id: str
    ) -> OrganizationMemberEntity:
        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one()
        row.suspended_at = datetime.now(UTC)
        await self._session.flush()
        return _to_org_member(row)

    async def reinstate_member(
        self, *, organization_id: str, user_id: str
    ) -> OrganizationMemberEntity:
        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one()
        row.suspended_at = None
        await self._session.flush()
        return _to_org_member(row)

    async def remove_member(self, *, organization_id: str, user_id: str) -> None:
        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one()
        await self._session.delete(row)
        await self._session.flush()

    async def count_owners(self, organization_id: str) -> int:
        stmt = select(func.count()).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.role == Role.OWNER,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_member_presence(self, organization_id: str) -> list[MemberPresence]:
        # Sessions are aggregated in SQL: MAX over each member's sessions
        # in one pass, rather than fetching every session row to reduce
        # them in Python. `expires_at > now` is the only honest "active"
        # signal available — there is no heartbeat to derive presence
        # from, and inventing one would be inventing a fact.
        now = datetime.now(UTC)
        latest_session = (
            select(
                Session.user_id.label("user_id"),
                func.max(Session.created_at).label("last_login_at"),
                func.max(Session.updated_at).label("last_seen_at"),
                func.count().filter(Session.expires_at > now).label("active_sessions"),
            )
            .group_by(Session.user_id)
            .subquery()
        )
        # The user agent/IP of the *most recent* session specifically,
        # which an aggregate cannot give — a separate correlated pick.
        newest = (
            select(Session.user_id, Session.user_agent, Session.ip_address)
            .distinct(Session.user_id)
            .order_by(Session.user_id, Session.created_at.desc())
            .subquery()
        )
        stmt = (
            select(
                User.id,
                User.email,
                User.name,
                OrganizationMember.role,
                OrganizationMember.suspended_at,
                latest_session.c.last_login_at,
                latest_session.c.last_seen_at,
                latest_session.c.active_sessions,
                newest.c.user_agent,
                newest.c.ip_address,
            )
            .select_from(OrganizationMember)
            .join(User, User.id == OrganizationMember.user_id)
            .join(latest_session, latest_session.c.user_id == User.id, isouter=True)
            .join(newest, newest.c.user_id == User.id, isouter=True)
            .where(OrganizationMember.organization_id == organization_id)
            .order_by(User.email)
        )
        result = await self._session.execute(stmt)
        return [
            MemberPresence(
                user_id=row.id,
                email=row.email,
                name=row.name,
                role=row.role,
                last_login_at=row.last_login_at,
                last_seen_at=row.last_seen_at,
                has_active_session=bool(row.active_sessions),
                last_user_agent=row.user_agent,
                last_ip_address=row.ip_address,
                suspended_at=row.suspended_at,
            )
            for row in result
        ]

    async def stats(self, organization_id: str) -> OrganizationStats:
        members = await self.list_members(organization_id)
        workspace_count = (
            await self._session.execute(
                select(func.count())
                .select_from(Workspace)
                .where(Workspace.organization_id == organization_id)
            )
        ).scalar_one()

        by_role: dict[Role, int] = {}
        for member in members:
            by_role[member.role] = by_role.get(member.role, 0) + 1
        suspended = sum(1 for member in members if member.suspended_at is not None)

        return OrganizationStats(
            workspace_count=int(workspace_count),
            member_count=len(members),
            active_member_count=len(members) - suspended,
            suspended_member_count=suspended,
            members_by_role=by_role,
        )

    async def list_members(self, organization_id: str) -> list[OrganizationMemberEntity]:
        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        return [_to_org_member(row) for row in result.scalars().all()]

    async def list_workspaces(self, organization_id: str) -> list[WorkspaceEntity]:
        stmt = select(Workspace).where(Workspace.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return [_to_workspace(row) for row in result.scalars().all()]

    async def attach_workspace(self, *, organization_id: str, workspace_id: str) -> None:
        row = await self._session.get(Workspace, workspace_id)
        assert row is not None
        row.organization_id = organization_id
        await self._session.flush()

    async def detach_workspace(self, *, workspace_id: str) -> None:
        row = await self._session.get(Workspace, workspace_id)
        if row is not None:
            row.organization_id = None
            await self._session.flush()


class SqlWorkspaceSettingsRepository:
    """Implements `domain.ports.WorkspaceSettingsRepository` against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, workspace_id: str) -> WorkspaceSettingsEntity | None:
        row = await self._session.get(WorkspaceSettings, workspace_id)
        return _to_workspace_settings(row) if row is not None else None

    async def upsert(
        self,
        *,
        workspace_id: str,
        logo_url: str | None,
        brand_color: str | None,
        custom_domain: str | None,
        retention_days: int | None,
        storage_limit_mb: int | None,
        updated_by_user_id: str,
    ) -> WorkspaceSettingsEntity:
        now = datetime.now(UTC)
        insert_stmt = pg_insert(WorkspaceSettings).values(
            workspace_id=workspace_id,
            logo_url=logo_url,
            brand_color=brand_color,
            custom_domain=custom_domain,
            retention_days=retention_days,
            storage_limit_mb=storage_limit_mb,
            updated_at=now,
            updated_by_user_id=updated_by_user_id,
        )
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=[WorkspaceSettings.workspace_id],
            set_={
                "logo_url": insert_stmt.excluded.logo_url,
                "brand_color": insert_stmt.excluded.brand_color,
                "custom_domain": insert_stmt.excluded.custom_domain,
                "retention_days": insert_stmt.excluded.retention_days,
                "storage_limit_mb": insert_stmt.excluded.storage_limit_mb,
                "updated_at": insert_stmt.excluded.updated_at,
                "updated_by_user_id": insert_stmt.excluded.updated_by_user_id,
            },
        ).returning(WorkspaceSettings)
        result = await self._session.execute(upsert_stmt)
        await self._session.flush()
        return _to_workspace_settings(result.scalar_one())


class SqlOrganizationSettingsRepository:
    """Implements `domain.ports.OrganizationSettingsRepository` against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: str) -> OrganizationSettingsEntity | None:
        row = await self._session.get(OrganizationSettings, organization_id)
        return _to_organization_settings(row) if row is not None else None

    async def upsert(
        self,
        *,
        organization_id: str,
        logo_url: str | None,
        brand_color: str | None,
        custom_domain: str | None,
        website_url: str | None,
        support_email: str | None,
        description: str | None,
        updated_by_user_id: str,
    ) -> OrganizationSettingsEntity:
        now = datetime.now(UTC)
        insert_stmt = pg_insert(OrganizationSettings).values(
            organization_id=organization_id,
            logo_url=logo_url,
            brand_color=brand_color,
            custom_domain=custom_domain,
            website_url=website_url,
            support_email=support_email,
            description=description,
            updated_at=now,
            updated_by_user_id=updated_by_user_id,
        )
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=[OrganizationSettings.organization_id],
            set_={
                "logo_url": insert_stmt.excluded.logo_url,
                "brand_color": insert_stmt.excluded.brand_color,
                "custom_domain": insert_stmt.excluded.custom_domain,
                "website_url": insert_stmt.excluded.website_url,
                "support_email": insert_stmt.excluded.support_email,
                "description": insert_stmt.excluded.description,
                "updated_at": insert_stmt.excluded.updated_at,
                "updated_by_user_id": insert_stmt.excluded.updated_by_user_id,
            },
        ).returning(OrganizationSettings)
        result = await self._session.execute(upsert_stmt)
        await self._session.flush()
        return _to_organization_settings(result.scalar_one())


def _to_security_event(row: SecurityEvent) -> SecurityEventEntity:
    return SecurityEventEntity(
        id=row.id,
        user_id=row.user_id,
        workspace_id=row.workspace_id,
        organization_id=row.organization_id,
        event_type=SecurityEventType(row.event_type),
        severity=SecuritySeverity(row.severity),
        ip_address=row.ip_address,
        user_agent=row.user_agent,
        metadata=row.event_metadata,
        created_at=row.created_at,
    )


def _to_trusted_device(row: TrustedDevice) -> TrustedDeviceEntity:
    return TrustedDeviceEntity(
        id=row.id,
        user_id=row.user_id,
        device_fingerprint=row.device_fingerprint,
        device_name=row.device_name,
        user_agent=row.user_agent,
        ip_address=row.ip_address,
        trusted_at=row.trusted_at,
        last_seen_at=row.last_seen_at,
        revoked_at=row.revoked_at,
    )


def _to_password_policy(row: PasswordPolicy) -> PasswordPolicyEntity:
    return PasswordPolicyEntity(
        min_length=row.min_length,
        require_uppercase=row.require_uppercase,
        require_lowercase=row.require_lowercase,
        require_number=row.require_number,
        require_symbol=row.require_symbol,
        max_age_days=row.max_age_days,
    )


class SqlSecurityEventRepository:
    """Implements `domain.ports.SecurityEventRepository` against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        user_id: str | None,
        workspace_id: str | None,
        organization_id: str | None,
        event_type: SecurityEventType,
        ip_address: str | None,
        user_agent: str | None,
        metadata: dict[str, str],
    ) -> SecurityEventEntity:
        row = SecurityEvent(
            id=str(uuid.uuid4()),
            user_id=user_id,
            workspace_id=workspace_id,
            organization_id=organization_id,
            event_type=event_type.value,
            # Derived, never caller-supplied: the same event recorded
            # from two code paths must land at the same severity or the
            # feed stops being sortable by urgency.
            severity=severity_for(event_type).value,
            ip_address=ip_address,
            user_agent=user_agent,
            event_metadata=metadata,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return _to_security_event(row)

    async def list_for_user(
        self,
        user_id: str,
        *,
        limit: int,
        severity: SecuritySeverity | None = None,
    ) -> list[SecurityEventEntity]:
        stmt = select(SecurityEvent).where(SecurityEvent.user_id == user_id)
        if severity is not None:
            stmt = stmt.where(SecurityEvent.severity == severity.value)
        stmt = stmt.order_by(SecurityEvent.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return [_to_security_event(row) for row in result.scalars()]

    async def list_for_workspace(
        self,
        workspace_id: str,
        *,
        limit: int,
        severity: SecuritySeverity | None = None,
    ) -> list[SecurityEventEntity]:
        stmt = select(SecurityEvent).where(SecurityEvent.workspace_id == workspace_id)
        if severity is not None:
            stmt = stmt.where(SecurityEvent.severity == severity.value)
        stmt = stmt.order_by(SecurityEvent.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return [_to_security_event(row) for row in result.scalars()]

    async def count_critical_since(self, workspace_id: str, *, since: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(SecurityEvent)
            .where(
                SecurityEvent.workspace_id == workspace_id,
                SecurityEvent.severity == SecuritySeverity.CRITICAL.value,
                SecurityEvent.created_at >= since,
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def count_recent_failures(self, *, user_id: str, since: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(SecurityEvent)
            .where(
                SecurityEvent.user_id == user_id,
                SecurityEvent.event_type == SecurityEventType.LOGIN_FAILED.value,
                SecurityEvent.created_at >= since,
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())


class SqlTrustedDeviceRepository:
    """Implements `domain.ports.TrustedDeviceRepository` against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        user_id: str,
        device_fingerprint: str,
        device_name: str | None,
        user_agent: str | None,
        ip_address: str | None,
    ) -> TrustedDeviceEntity:
        now = datetime.now(UTC)
        insert_stmt = pg_insert(TrustedDevice).values(
            id=str(uuid.uuid4()),
            user_id=user_id,
            device_fingerprint=device_fingerprint,
            device_name=device_name,
            user_agent=user_agent,
            ip_address=ip_address,
            trusted_at=now,
            last_seen_at=now,
            revoked_at=None,
        )
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=[TrustedDevice.user_id, TrustedDevice.device_fingerprint],
            set_={
                "device_name": insert_stmt.excluded.device_name,
                "user_agent": insert_stmt.excluded.user_agent,
                "ip_address": insert_stmt.excluded.ip_address,
                "last_seen_at": insert_stmt.excluded.last_seen_at,
                # Re-trusting a previously revoked device un-revokes it,
                # rather than leaving a row that reads as trusted while
                # still being refused.
                "revoked_at": None,
            },
        ).returning(TrustedDevice)
        result = await self._session.execute(upsert_stmt)
        await self._session.flush()
        return _to_trusted_device(result.scalar_one())

    async def get(self, *, user_id: str, device_fingerprint: str) -> TrustedDeviceEntity | None:
        stmt = select(TrustedDevice).where(
            TrustedDevice.user_id == user_id,
            TrustedDevice.device_fingerprint == device_fingerprint,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_trusted_device(row) if row is not None else None

    async def list_for_user(self, user_id: str) -> list[TrustedDeviceEntity]:
        stmt = (
            select(TrustedDevice)
            .where(TrustedDevice.user_id == user_id)
            .order_by(TrustedDevice.last_seen_at.desc())
        )
        result = await self._session.execute(stmt)
        return [_to_trusted_device(row) for row in result.scalars()]

    async def revoke(self, *, user_id: str, device_id: str) -> TrustedDeviceEntity | None:
        # Scoped by user_id as well as id: a device id from another
        # account must read as "no such device", never revoke someone
        # else's (Rule 11 — never trust a client-supplied id alone).
        stmt = select(TrustedDevice).where(
            TrustedDevice.id == device_id, TrustedDevice.user_id == user_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        if row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)
            await self._session.flush()
        return _to_trusted_device(row)


class SqlPasswordPolicyRepository:
    """Implements `domain.ports.PasswordPolicyRepository` against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: str) -> PasswordPolicyEntity | None:
        row = await self._session.get(PasswordPolicy, organization_id)
        return _to_password_policy(row) if row is not None else None

    async def upsert(
        self,
        *,
        organization_id: str,
        policy: PasswordPolicyEntity,
        updated_by_user_id: str,
    ) -> PasswordPolicyEntity:
        now = datetime.now(UTC)
        insert_stmt = pg_insert(PasswordPolicy).values(
            organization_id=organization_id,
            min_length=policy.min_length,
            require_uppercase=policy.require_uppercase,
            require_lowercase=policy.require_lowercase,
            require_number=policy.require_number,
            require_symbol=policy.require_symbol,
            max_age_days=policy.max_age_days,
            updated_at=now,
            updated_by_user_id=updated_by_user_id,
        )
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=[PasswordPolicy.organization_id],
            set_={
                "min_length": insert_stmt.excluded.min_length,
                "require_uppercase": insert_stmt.excluded.require_uppercase,
                "require_lowercase": insert_stmt.excluded.require_lowercase,
                "require_number": insert_stmt.excluded.require_number,
                "require_symbol": insert_stmt.excluded.require_symbol,
                "max_age_days": insert_stmt.excluded.max_age_days,
                "updated_at": insert_stmt.excluded.updated_at,
                "updated_by_user_id": insert_stmt.excluded.updated_by_user_id,
            },
        ).returning(PasswordPolicy)
        result = await self._session.execute(upsert_stmt)
        await self._session.flush()
        return _to_password_policy(result.scalar_one())


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
        scope: ApiKeyScope = ApiKeyScope.FULL,
        tier: str = "standard",
        rotated_from_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> ApiKeyEntity:
        row = ApiKey(
            workspace_id=workspace_id,
            name=name,
            key_prefix=key_prefix,
            hashed_key=hashed_key,
            created_by_user_id=created_by_user_id,
            created_at=datetime.now(UTC),
            scope=scope.value,
            tier=tier,
            rotated_from_id=rotated_from_id,
            expires_at=expires_at,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_api_key(row)

    async def list_api_keys(self, workspace_id: str) -> list[ApiKeyEntity]:
        stmt = select(ApiKey).where(ApiKey.workspace_id == workspace_id)
        result = await self._session.execute(stmt)
        return [_to_api_key(row) for row in result.scalars().all()]

    async def count_non_expiring(self, workspace_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(ApiKey)
            .where(
                ApiKey.workspace_id == workspace_id,
                ApiKey.revoked_at.is_(None),
                ApiKey.expires_at.is_(None),
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def get_api_key(self, api_key_id: str) -> ApiKeyEntity | None:
        row = await self._session.get(ApiKey, api_key_id)
        return _to_api_key(row) if row is not None else None

    async def revoke_api_key(self, api_key_id: str) -> None:
        row = await self._session.get(ApiKey, api_key_id)
        if row is not None:
            row.revoked_at = datetime.now(UTC)
            await self._session.flush()

    async def find_active_by_hash(self, hashed_key: str) -> ApiKeyEntity | None:
        # `hashed_key` is UNIQUE, so this is an index lookup on the
        # authentication hot path, not a scan.
        #
        # Expiry is filtered in SQL rather than checked by the caller
        # afterwards: an expired key must be indistinguishable from an
        # unknown one, and a caller that forgot the check would silently
        # accept it.
        stmt = select(ApiKey).where(
            ApiKey.hashed_key == hashed_key,
            ApiKey.revoked_at.is_(None),
            sa_or(ApiKey.expires_at.is_(None), ApiKey.expires_at > datetime.now(UTC)),
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _to_api_key(row) if row is not None else None

    async def touch_last_used(self, api_key_id: str) -> None:
        stmt = (
            update(ApiKey)
            .where(ApiKey.id == api_key_id)
            .values(last_used_at=datetime.now(UTC), use_count=ApiKey.use_count + 1)
        )
        await self._session.execute(stmt)


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
        organization_id: str | None = None,
    ) -> AuditLogEntry:
        row = AuditLog(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            target=target,
            outcome=outcome,
            log_metadata=metadata,
            created_at=datetime.now(UTC),
            organization_id=organization_id,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_audit_entry(row)

    async def list_for_workspace(
        self,
        *,
        workspace_id: str,
        limit: int,
        cursor: str | None,
        action: str | None,
        actor_user_id: str | None,
        since: datetime | None,
        until: datetime | None,
    ) -> list[AuditLogEntry]:
        statement = select(AuditLog).where(AuditLog.workspace_id == workspace_id)
        if action:
            statement = statement.where(AuditLog.action == action)
        if actor_user_id:
            statement = statement.where(AuditLog.actor_user_id == actor_user_id)
        if since:
            statement = statement.where(AuditLog.created_at >= since)
        if until:
            statement = statement.where(AuditLog.created_at <= until)
        if cursor:
            # Keyset on `created_at`, matching the `tool_calls` runtime-log
            # convention (CLAUDE.md §7) — offset pagination on a
            # fast-appending, append-only table skips and repeats rows.
            statement = statement.where(AuditLog.created_at < datetime.fromisoformat(cursor))
        result = await self._session.execute(
            statement.order_by(AuditLog.created_at.desc()).limit(limit)
        )
        return [_to_audit_entry(row) for row in result.scalars()]

    async def count_by_day(self, workspace_id: str, *, since: datetime) -> list[tuple[date, int]]:
        day = func.date_trunc("day", AuditLog.created_at).label("day")
        stmt = (
            select(day, func.count().label("entries"))
            .where(AuditLog.workspace_id == workspace_id, AuditLog.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
        result = await self._session.execute(stmt)
        return [(row.day.date(), int(row.entries)) for row in result]


class SqlInvitationRepository:
    """Implements `domain.ports.InvitationRepository` against Postgres —
    reads/writes Better Auth's `verifications` table (ADR-0005), never
    the domain rows Better Auth itself manages there.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        target_type: InvitationTargetType,
        target_id: str,
        role: Role,
        inviter_user_id: str,
        email: str,
        token: str,
        expires_at: datetime,
    ) -> Invitation:
        now = datetime.now(UTC)
        row = Verification(
            id=str(uuid.uuid4()),
            identifier=_build_invitation_identifier(
                target_type=target_type,
                target_id=target_id,
                role=role,
                inviter_user_id=inviter_user_id,
                email=email,
            ),
            value=token,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        invitation = _to_invitation(row)
        assert invitation is not None
        return invitation

    async def get_by_token(self, token: str) -> Invitation | None:
        stmt = select(Verification).where(Verification.value == token)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _to_invitation(row) if row is not None else None

    async def consume(self, token: str) -> None:
        stmt = select(Verification).where(Verification.value == token)
        result = await self._session.execute(stmt)
        row = result.scalar_one()
        row.consumed_at = datetime.now(UTC)
        await self._session.flush()


class SqlUserLookupRepository:
    """Implements `domain.ports.UserLookupRepository` against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> UserSummary | None:
        stmt = select(User).where(func.lower(User.email) == email.lower())
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return UserSummary(id=row.id, email=row.email) if row is not None else None

    async def get_by_id(self, user_id: str) -> UserSummary | None:
        row = await self._session.get(User, user_id)
        return UserSummary(id=row.id, email=row.email) if row is not None else None


def _to_resource_permission(row: ResourcePermission) -> ResourcePermissionEntity:
    return ResourcePermissionEntity(
        id=row.id,
        workspace_id=row.workspace_id,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        principal_type=row.principal_type,
        principal_id=row.principal_id,
        permission=row.permission,
        granted_by_user_id=row.granted_by_user_id,
        created_at=row.created_at,
    )


class SqlResourcePermissionRepository:
    """Implements `domain.ports.ResourcePermissionRepository` against
    Postgres.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def grant(
        self,
        *,
        workspace_id: str,
        resource_type: str,
        resource_id: str,
        principal_type: str,
        principal_id: str,
        permission: str,
        granted_by_user_id: str,
    ) -> ResourcePermissionEntity:
        insert_stmt = pg_insert(ResourcePermission).values(
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
            principal_type=principal_type,
            principal_id=principal_id,
            permission=permission,
            granted_by_user_id=granted_by_user_id,
            created_at=datetime.now(UTC),
        )
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=[
                ResourcePermission.workspace_id,
                ResourcePermission.resource_type,
                ResourcePermission.resource_id,
                ResourcePermission.principal_type,
                ResourcePermission.principal_id,
                ResourcePermission.permission,
            ],
            set_={"granted_by_user_id": insert_stmt.excluded.granted_by_user_id},
        ).returning(ResourcePermission)
        result = await self._session.execute(upsert_stmt)
        await self._session.flush()
        return _to_resource_permission(result.scalar_one())

    async def revoke_by_id(self, *, workspace_id: str, permission_id: str) -> None:
        stmt = select(ResourcePermission).where(
            ResourcePermission.id == permission_id,
            ResourcePermission.workspace_id == workspace_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    async def check(
        self,
        *,
        workspace_id: str,
        resource_type: str,
        resource_id: str,
        principal_type: str,
        principal_id: str,
        permission: str,
    ) -> bool:
        stmt = select(ResourcePermission.id).where(
            ResourcePermission.workspace_id == workspace_id,
            ResourcePermission.resource_type == resource_type,
            ResourcePermission.resource_id == resource_id,
            ResourcePermission.principal_type == principal_type,
            ResourcePermission.principal_id == principal_id,
            ResourcePermission.permission == permission,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_for_workspace(self, workspace_id: str) -> list[ResourcePermissionEntity]:
        stmt = select(ResourcePermission).where(ResourcePermission.workspace_id == workspace_id)
        result = await self._session.execute(stmt)
        return [_to_resource_permission(row) for row in result.scalars().all()]


def _to_ip_entry(row: WorkspaceIpAllowlist) -> IpAllowlistEntry:
    return IpAllowlistEntry(
        id=row.id,
        workspace_id=row.workspace_id,
        cidr=row.cidr,
        label=row.label,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


class SqlIpAllowlistRepository:
    """Implements `domain.ports.IpAllowlistRepository` against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_workspace(self, workspace_id: str) -> list[IpAllowlistEntry]:
        stmt = select(WorkspaceIpAllowlist).where(WorkspaceIpAllowlist.workspace_id == workspace_id)
        result = await self._session.execute(stmt)
        return [_to_ip_entry(row) for row in result.scalars().all()]

    async def add(
        self, *, workspace_id: str, cidr: str, label: str | None, created_by_user_id: str
    ) -> IpAllowlistEntry:
        row = WorkspaceIpAllowlist(
            workspace_id=workspace_id,
            cidr=cidr,
            label=label,
            created_by_user_id=created_by_user_id,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return _to_ip_entry(row)

    async def remove_by_id(self, *, workspace_id: str, entry_id: str) -> None:
        stmt = select(WorkspaceIpAllowlist).where(
            WorkspaceIpAllowlist.id == entry_id,
            WorkspaceIpAllowlist.workspace_id == workspace_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()


def _to_sso_config(row: SsoConfiguration) -> SsoConfigurationEntity:
    return SsoConfigurationEntity(
        id=row.id,
        organization_id=row.organization_id,
        protocol=SsoProtocol(row.protocol),
        preset=SsoPreset(row.preset),
        issuer_url=row.issuer_url,
        client_id=row.client_id,
        has_client_secret=row.client_secret_ciphertext is not None,
        protocol_config=row.protocol_config,
        enabled=row.enabled,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlSsoConfigurationRepository:
    """Implements `domain.ports.SsoConfigurationRepository` against
    Postgres. Never returns the client secret — see the entity docstring.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_organization(self, organization_id: str) -> list[SsoConfigurationEntity]:
        stmt = select(SsoConfiguration).where(SsoConfiguration.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return [_to_sso_config(row) for row in result.scalars().all()]

    async def get(self, *, organization_id: str, config_id: str) -> SsoConfigurationEntity | None:
        stmt = select(SsoConfiguration).where(
            SsoConfiguration.id == config_id,
            SsoConfiguration.organization_id == organization_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _to_sso_config(row) if row is not None else None

    async def upsert(
        self,
        *,
        organization_id: str,
        protocol: SsoProtocol,
        preset: SsoPreset,
        issuer_url: str | None,
        client_id: str | None,
        sealed_secret: tuple[bytes, bytes, str] | None,
        protocol_config: dict[str, str],
        enabled: bool,
        actor_user_id: str,
    ) -> SsoConfigurationEntity:
        now = datetime.now(UTC)
        stmt = select(SsoConfiguration).where(
            SsoConfiguration.organization_id == organization_id,
            SsoConfiguration.protocol == protocol.value,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            row = SsoConfiguration(
                organization_id=organization_id,
                protocol=protocol.value,
                preset=preset.value,
                issuer_url=issuer_url,
                client_id=client_id,
                protocol_config=protocol_config,
                enabled=enabled,
                created_by_user_id=actor_user_id,
                created_at=now,
                updated_at=now,
            )
            self._session.add(row)
        else:
            row.preset = preset.value
            row.issuer_url = issuer_url
            row.client_id = client_id
            row.protocol_config = protocol_config
            row.enabled = enabled
            row.updated_at = now

        if sealed_secret is not None:
            ciphertext, wrapped_dek, key_version = sealed_secret
            row.client_secret_ciphertext = ciphertext
            row.wrapped_dek = wrapped_dek
            row.key_version = key_version

        await self._session.flush()
        return _to_sso_config(row)

    async def list_enabled_sealed(
        self, protocol: SsoProtocol
    ) -> list[tuple[SsoConfigurationEntity, tuple[bytes, bytes, str] | None]]:
        stmt = select(SsoConfiguration).where(
            SsoConfiguration.protocol == protocol.value,
            SsoConfiguration.enabled.is_(True),
        )
        result = await self._session.execute(stmt)
        pairs: list[tuple[SsoConfigurationEntity, tuple[bytes, bytes, str] | None]] = []
        for row in result.scalars().all():
            sealed = (
                (row.client_secret_ciphertext, row.wrapped_dek, row.key_version)
                if row.client_secret_ciphertext is not None
                and row.wrapped_dek is not None
                and row.key_version is not None
                else None
            )
            pairs.append((_to_sso_config(row), sealed))
        return pairs

    async def delete(self, *, organization_id: str, config_id: str) -> None:
        stmt = select(SsoConfiguration).where(
            SsoConfiguration.id == config_id,
            SsoConfiguration.organization_id == organization_id,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()


def _to_scim_user(user: User, member: OrganizationMember) -> ScimUser:
    return ScimUser(
        user_id=user.id,
        email=user.email,
        display_name=user.name,
        role=member.role,
        active=member.suspended_at is None,
        created_at=member.created_at,
    )


def _to_scim_token(row: ScimToken) -> ScimTokenEntity:
    return ScimTokenEntity(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        token_prefix=row.token_prefix,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
    )


class SqlScimTokenRepository:
    """Implements `domain.ports.ScimTokenRepository` against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        organization_id: str,
        name: str,
        token_prefix: str,
        hashed_token: str,
        created_by_user_id: str,
    ) -> ScimTokenEntity:
        row = ScimToken(
            organization_id=organization_id,
            name=name,
            token_prefix=token_prefix,
            hashed_token=hashed_token,
            created_by_user_id=created_by_user_id,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return _to_scim_token(row)

    async def list_for_organization(self, organization_id: str) -> list[ScimTokenEntity]:
        stmt = select(ScimToken).where(ScimToken.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return [_to_scim_token(row) for row in result.scalars().all()]

    async def find_active_by_hash(self, hashed_token: str) -> ScimTokenEntity | None:
        # `hashed_token` is UNIQUE — an index lookup on the SCIM
        # authentication hot path, not a scan.
        stmt = select(ScimToken).where(
            ScimToken.hashed_token == hashed_token, ScimToken.revoked_at.is_(None)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return _to_scim_token(row) if row is not None else None

    async def touch_last_used(self, token_id: str) -> None:
        await self._session.execute(
            update(ScimToken).where(ScimToken.id == token_id).values(last_used_at=datetime.now(UTC))
        )

    async def revoke(self, *, organization_id: str, token_id: str) -> bool:
        stmt = select(ScimToken).where(
            ScimToken.id == token_id, ScimToken.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return False
        row.revoked_at = datetime.now(UTC)
        await self._session.flush()
        return True


class SqlScimRepository:
    """Implements `domain.ports.ScimRepository` against Postgres.

    Every read and write is filtered by `organization_id` — a SCIM token
    holder can only ever see or touch identities inside its own
    organization (Rule 11).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _membership_query(self, organization_id: str):  # type: ignore[no-untyped-def]
        return (
            select(User, OrganizationMember)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .where(OrganizationMember.organization_id == organization_id)
        )

    async def list_users(
        self, *, organization_id: str, email: str | None, start_index: int, count: int
    ) -> tuple[list[ScimUser], int]:
        stmt = self._membership_query(organization_id)
        if email is not None:
            stmt = stmt.where(func.lower(User.email) == email.lower())

        total_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self._session.execute(total_stmt)).scalar_one())

        # SCIM's `startIndex` is 1-based, unlike SQL's OFFSET.
        page = stmt.order_by(User.email).offset(max(start_index - 1, 0)).limit(count)
        rows = (await self._session.execute(page)).all()
        return [_to_scim_user(user, member) for user, member in rows], total

    async def get_user(self, *, organization_id: str, user_id: str) -> ScimUser | None:
        stmt = self._membership_query(organization_id).where(User.id == user_id)
        row = (await self._session.execute(stmt)).one_or_none()
        return None if row is None else _to_scim_user(row[0], row[1])

    async def create_user(
        self, *, organization_id: str, email: str, display_name: str, role: Role
    ) -> ScimUser:
        now = datetime.now(UTC)
        existing = (
            await self._session.execute(select(User).where(func.lower(User.email) == email.lower()))
        ).scalar_one_or_none()

        if existing is None:
            user = User(
                id=str(uuid.uuid4()),
                name=display_name,
                email=email,
                # The IdP authenticated this address before provisioning
                # it; requiring a second AgentVerse-side verification
                # would leave SCIM-created users unable to sign in at
                # all. Same reasoning as the SSO JIT path.
                email_verified=True,
                created_at=now,
                updated_at=now,
            )
            self._session.add(user)
            await self._session.flush()
        else:
            user = existing

        member = (
            await self._session.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == organization_id,
                    OrganizationMember.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if member is None:
            member = OrganizationMember(
                organization_id=organization_id,
                user_id=user.id,
                role=role,
                created_at=now,
            )
            self._session.add(member)
        else:
            # Re-provisioning someone previously deactivated reactivates
            # them rather than erroring — SCIM clients retry, and a
            # duplicate POST must be safe.
            member.suspended_at = None
        await self._session.flush()
        return _to_scim_user(user, member)

    async def set_active(
        self, *, organization_id: str, user_id: str, active: bool
    ) -> ScimUser | None:
        member = (
            await self._session.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == organization_id,
                    OrganizationMember.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if member is None:
            return None
        member.suspended_at = None if active else datetime.now(UTC)
        await self._session.flush()
        return await self.get_user(organization_id=organization_id, user_id=user_id)

    async def set_display_name(
        self, *, organization_id: str, user_id: str, display_name: str
    ) -> ScimUser | None:
        current = await self.get_user(organization_id=organization_id, user_id=user_id)
        if current is None:
            return None
        await self._session.execute(
            update(User)
            .where(User.id == user_id)
            .values(name=display_name, updated_at=datetime.now(UTC))
        )
        await self._session.flush()
        return await self.get_user(organization_id=organization_id, user_id=user_id)

    async def remove_user(self, *, organization_id: str, user_id: str) -> bool:
        member = (
            await self._session.execute(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == organization_id,
                    OrganizationMember.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if member is None:
            return False
        # Deprovisioning removes the *membership*, never the account: the
        # same person may belong to other organizations, and their runs
        # and audit entries reference the user row.
        await self._session.delete(member)
        await self._session.flush()
        return True

    async def list_groups(self, organization_id: str) -> list[WorkspaceEntity]:
        stmt = select(Workspace).where(Workspace.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return [_to_workspace(row) for row in result.scalars().all()]

    async def get_group(self, *, organization_id: str, workspace_id: str) -> WorkspaceEntity | None:
        stmt = select(Workspace).where(
            Workspace.id == workspace_id, Workspace.organization_id == organization_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if row is None else _to_workspace(row)


def _to_custom_role(row: CustomRoleModel, permissions: tuple[str, ...]) -> CustomRoleEntity:
    return CustomRoleEntity(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        description=row.description,
        base_role=row.base_role,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        permissions=permissions,
    )


class SqlCustomRoleRepository:
    """Tenant-defined roles. Every query filters on `workspace_id` — the
    role id alone is never a sufficient key (Rule 11).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _permissions_for(self, role_id: str) -> tuple[str, ...]:
        stmt = select(CustomRolePermissionModel.permission).where(
            CustomRolePermissionModel.role_id == role_id
        )
        result = await self._session.execute(stmt)
        return tuple(sorted(result.scalars().all()))

    async def _replace_permissions(self, role_id: str, permissions: list[str]) -> None:
        await self._session.execute(
            sa_delete(CustomRolePermissionModel).where(CustomRolePermissionModel.role_id == role_id)
        )
        now = datetime.now(UTC)
        for permission in sorted(set(permissions)):
            self._session.add(
                CustomRolePermissionModel(
                    id=str(uuid.uuid4()),
                    role_id=role_id,
                    permission=permission,
                    created_at=now,
                )
            )

    async def create(
        self,
        *,
        workspace_id: str,
        name: str,
        description: str | None,
        base_role: Role,
        permissions: list[str],
        created_by_user_id: str,
    ) -> CustomRoleEntity:
        role_id = str(uuid.uuid4())
        self._session.add(
            CustomRoleModel(
                id=role_id,
                workspace_id=workspace_id,
                name=name,
                description=description,
                base_role=base_role,
                created_by_user_id=created_by_user_id,
                created_at=datetime.now(UTC),
                updated_at=None,
            )
        )
        await self._session.flush()
        await self._replace_permissions(role_id, permissions)
        await self._session.flush()
        row = (
            await self._session.execute(
                select(CustomRoleModel).where(CustomRoleModel.id == role_id)
            )
        ).scalar_one()
        return _to_custom_role(row, await self._permissions_for(role_id))

    async def get(self, *, workspace_id: str, role_id: str) -> CustomRoleEntity | None:
        stmt = select(CustomRoleModel).where(
            CustomRoleModel.id == role_id, CustomRoleModel.workspace_id == workspace_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return _to_custom_role(row, await self._permissions_for(role_id))

    async def update(
        self,
        *,
        workspace_id: str,
        role_id: str,
        name: str | None,
        description: str | None,
        base_role: Role | None,
        permissions: list[str] | None,
    ) -> CustomRoleEntity:
        stmt = select(CustomRoleModel).where(
            CustomRoleModel.id == role_id, CustomRoleModel.workspace_id == workspace_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise CustomRoleNotFoundError(role_id)

        if name is not None:
            row.name = name
        if description is not None:
            row.description = description
        if base_role is not None:
            row.base_role = base_role
        row.updated_at = datetime.now(UTC)

        if permissions is not None:
            await self._replace_permissions(role_id, permissions)
        await self._session.flush()
        return _to_custom_role(row, await self._permissions_for(role_id))

    async def delete(self, *, workspace_id: str, role_id: str) -> None:
        stmt = select(CustomRoleModel).where(
            CustomRoleModel.id == role_id, CustomRoleModel.workspace_id == workspace_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise CustomRoleNotFoundError(role_id)
        # `workspace_members.custom_role_id` is ON DELETE SET NULL, so
        # members holding this role fall back to their `role` base tier
        # rather than losing workspace access entirely.
        await self._session.delete(row)
        await self._session.flush()

    async def list_for_workspace(self, workspace_id: str) -> list[CustomRoleEntity]:
        stmt = (
            select(CustomRoleModel)
            .where(CustomRoleModel.workspace_id == workspace_id)
            .order_by(CustomRoleModel.created_at)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_custom_role(row, await self._permissions_for(row.id)) for row in rows]

    async def list_permissions(self, *, workspace_id: str, role_id: str) -> frozenset[Permission]:
        # Joined to `roles` so the workspace filter applies — reading the
        # grant table by `role_id` alone would answer for another
        # tenant's role.
        stmt = (
            select(CustomRolePermissionModel.permission)
            .join(CustomRoleModel, CustomRoleModel.id == CustomRolePermissionModel.role_id)
            .where(
                CustomRoleModel.id == role_id,
                CustomRoleModel.workspace_id == workspace_id,
            )
        )
        result = await self._session.execute(stmt)
        resolved: set[Permission] = set()
        for value in result.scalars().all():
            try:
                resolved.add(Permission(value))
            except ValueError:
                # A grant row whose permission no longer exists in the
                # enum (removed in a later release). Skipped rather than
                # raised: authorization must fail closed, and a 500 here
                # would take out every request the member makes.
                continue
        return frozenset(resolved)
