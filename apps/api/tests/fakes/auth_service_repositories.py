"""In-memory fakes implementing `auth_service.domain.ports` — used by
unit tests so application-layer logic is tested without I/O
(CLAUDE.md §11). Integration tests use the real `Sql*Repository`
classes against Postgres instead; these fakes are never used there.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from agentverse_api.auth_service.domain.api_key_scope import ApiKeyScope
from agentverse_api.auth_service.domain.entities import (
    ApiKey,
    AuditLogEntry,
    Invitation,
    IpAllowlistEntry,
    Organization,
    OrganizationMember,
    OrganizationSummary,
    ResourcePermission,
    UserSummary,
    Workspace,
    WorkspaceMember,
    WorkspaceSettings,
    WorkspaceSummary,
)
from agentverse_api.auth_service.domain.invitation_target_type import InvitationTargetType
from agentverse_api.auth_service.domain.role import Role


@dataclass
class FakeWorkspaceRepository:
    workspaces: dict[str, Workspace] = field(default_factory=dict)
    members: dict[tuple[str, str], WorkspaceMember] = field(default_factory=dict)

    async def create_workspace(self, *, name: str, slug: str, owner_user_id: str) -> Workspace:
        now = datetime.now(UTC)
        workspace = Workspace(id=str(uuid.uuid4()), name=name, slug=slug, created_at=now)
        self.workspaces[workspace.id] = workspace
        self.members[(workspace.id, owner_user_id)] = WorkspaceMember(
            workspace_id=workspace.id, user_id=owner_user_id, role=Role.OWNER, created_at=now
        )
        return workspace

    async def get_workspace(self, workspace_id: str) -> Workspace | None:
        return self.workspaces.get(workspace_id)

    async def list_for_user(self, user_id: str) -> list[WorkspaceSummary]:
        return [
            WorkspaceSummary(workspace=self.workspaces[workspace_id], role=member.role)
            for (workspace_id, uid), member in self.members.items()
            if uid == user_id
        ]

    async def slug_exists(self, slug: str) -> bool:
        return any(workspace.slug == slug for workspace in self.workspaces.values())

    async def get_membership(self, *, workspace_id: str, user_id: str) -> WorkspaceMember | None:
        return self.members.get((workspace_id, user_id))

    async def add_member(self, *, workspace_id: str, user_id: str, role: Role) -> WorkspaceMember:
        member = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=role, created_at=datetime.now(UTC)
        )
        self.members[(workspace_id, user_id)] = member
        return member

    async def update_member_role(
        self, *, workspace_id: str, user_id: str, role: Role
    ) -> WorkspaceMember:
        existing = self.members[(workspace_id, user_id)]
        updated = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=role, created_at=existing.created_at
        )
        self.members[(workspace_id, user_id)] = updated
        return updated

    async def remove_member(self, *, workspace_id: str, user_id: str) -> None:
        del self.members[(workspace_id, user_id)]

    async def count_owners(self, workspace_id: str) -> int:
        return sum(
            1
            for (wid, _uid), member in self.members.items()
            if wid == workspace_id and member.role is Role.OWNER
        )

    async def list_members(self, workspace_id: str) -> list[WorkspaceMember]:
        return [member for (wid, _uid), member in self.members.items() if wid == workspace_id]


@dataclass
class FakeOrganizationRepository:
    organizations: dict[str, Organization] = field(default_factory=dict)
    members: dict[tuple[str, str], OrganizationMember] = field(default_factory=dict)
    workspaces: dict[str, Workspace] = field(default_factory=dict)

    async def create_organization(
        self, *, name: str, slug: str, owner_user_id: str
    ) -> Organization:
        now = datetime.now(UTC)
        organization = Organization(id=str(uuid.uuid4()), name=name, slug=slug, created_at=now)
        self.organizations[organization.id] = organization
        self.members[(organization.id, owner_user_id)] = OrganizationMember(
            organization_id=organization.id, user_id=owner_user_id, role=Role.OWNER, created_at=now
        )
        return organization

    async def get_organization(self, organization_id: str) -> Organization | None:
        return self.organizations.get(organization_id)

    async def list_for_user(self, user_id: str) -> list[OrganizationSummary]:
        return [
            OrganizationSummary(organization=self.organizations[organization_id], role=member.role)
            for (organization_id, uid), member in self.members.items()
            if uid == user_id
        ]

    async def slug_exists(self, slug: str) -> bool:
        return any(organization.slug == slug for organization in self.organizations.values())

    async def rename_organization(self, *, organization_id: str, name: str) -> Organization:
        existing = self.organizations[organization_id]
        updated = Organization(
            id=existing.id, name=name, slug=existing.slug, created_at=existing.created_at
        )
        self.organizations[organization_id] = updated
        return updated

    async def delete_organization(self, organization_id: str) -> None:
        self.organizations.pop(organization_id, None)
        for key in [key for key in self.members if key[0] == organization_id]:
            del self.members[key]
        for workspace_id, workspace in list(self.workspaces.items()):
            if workspace.organization_id == organization_id:
                self.workspaces[workspace_id] = Workspace(
                    id=workspace.id,
                    name=workspace.name,
                    slug=workspace.slug,
                    created_at=workspace.created_at,
                    organization_id=None,
                )

    async def get_membership(
        self, *, organization_id: str, user_id: str
    ) -> OrganizationMember | None:
        return self.members.get((organization_id, user_id))

    async def add_member(
        self, *, organization_id: str, user_id: str, role: Role
    ) -> OrganizationMember:
        member = OrganizationMember(
            organization_id=organization_id,
            user_id=user_id,
            role=role,
            created_at=datetime.now(UTC),
        )
        self.members[(organization_id, user_id)] = member
        return member

    async def update_member_role(
        self, *, organization_id: str, user_id: str, role: Role
    ) -> OrganizationMember:
        existing = self.members[(organization_id, user_id)]
        updated = OrganizationMember(
            organization_id=organization_id,
            user_id=user_id,
            role=role,
            created_at=existing.created_at,
            suspended_at=existing.suspended_at,
        )
        self.members[(organization_id, user_id)] = updated
        return updated

    async def suspend_member(self, *, organization_id: str, user_id: str) -> OrganizationMember:
        existing = self.members[(organization_id, user_id)]
        updated = OrganizationMember(
            organization_id=organization_id,
            user_id=user_id,
            role=existing.role,
            created_at=existing.created_at,
            suspended_at=datetime.now(UTC),
        )
        self.members[(organization_id, user_id)] = updated
        return updated

    async def reinstate_member(self, *, organization_id: str, user_id: str) -> OrganizationMember:
        existing = self.members[(organization_id, user_id)]
        updated = OrganizationMember(
            organization_id=organization_id,
            user_id=user_id,
            role=existing.role,
            created_at=existing.created_at,
            suspended_at=None,
        )
        self.members[(organization_id, user_id)] = updated
        return updated

    async def remove_member(self, *, organization_id: str, user_id: str) -> None:
        del self.members[(organization_id, user_id)]

    async def count_owners(self, organization_id: str) -> int:
        return sum(
            1
            for (oid, _uid), member in self.members.items()
            if oid == organization_id and member.role is Role.OWNER
        )

    async def list_members(self, organization_id: str) -> list[OrganizationMember]:
        return [member for (oid, _uid), member in self.members.items() if oid == organization_id]

    async def list_workspaces(self, organization_id: str) -> list[Workspace]:
        return [
            workspace
            for workspace in self.workspaces.values()
            if workspace.organization_id == organization_id
        ]

    async def attach_workspace(self, *, organization_id: str, workspace_id: str) -> None:
        existing = self.workspaces[workspace_id]
        self.workspaces[workspace_id] = Workspace(
            id=existing.id,
            name=existing.name,
            slug=existing.slug,
            created_at=existing.created_at,
            organization_id=organization_id,
        )

    async def detach_workspace(self, *, workspace_id: str) -> None:
        existing = self.workspaces.get(workspace_id)
        if existing is not None:
            self.workspaces[workspace_id] = Workspace(
                id=existing.id,
                name=existing.name,
                slug=existing.slug,
                created_at=existing.created_at,
                organization_id=None,
            )


@dataclass
class FakeApiKeyRepository:
    keys: dict[str, ApiKey] = field(default_factory=dict)

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
    ) -> ApiKey:
        key = ApiKey(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            name=name,
            key_prefix=key_prefix,
            hashed_key=hashed_key,
            created_by_user_id=created_by_user_id,
            created_at=datetime.now(UTC),
            last_used_at=None,
            revoked_at=None,
            scope=scope,
            tier=tier,
            rotated_from_id=rotated_from_id,
        )
        self.keys[key.id] = key
        return key

    async def list_api_keys(self, workspace_id: str) -> list[ApiKey]:
        return [key for key in self.keys.values() if key.workspace_id == workspace_id]

    async def get_api_key(self, api_key_id: str) -> ApiKey | None:
        return self.keys.get(api_key_id)

    async def revoke_api_key(self, api_key_id: str) -> None:
        key = self.keys[api_key_id]
        self.keys[api_key_id] = ApiKey(
            id=key.id,
            workspace_id=key.workspace_id,
            name=key.name,
            key_prefix=key.key_prefix,
            hashed_key=key.hashed_key,
            created_by_user_id=key.created_by_user_id,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            revoked_at=datetime.now(UTC),
            scope=key.scope,
            tier=key.tier,
            rotated_from_id=key.rotated_from_id,
        )

    async def find_active_by_hash(self, hashed_key: str) -> ApiKey | None:
        for key in self.keys.values():
            if key.hashed_key == hashed_key and key.revoked_at is None:
                return key
        return None

    async def touch_last_used(self, api_key_id: str) -> None:
        key = self.keys.get(api_key_id)
        if key is None:
            return
        self.keys[api_key_id] = replace(key, last_used_at=datetime.now(UTC))


@dataclass
class FakeAuditLogRepository:
    entries: list[AuditLogEntry] = field(default_factory=list)

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
        entry = AuditLogEntry(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            target=target,
            outcome=outcome,
            metadata=metadata,
            created_at=datetime.now(UTC),
            organization_id=organization_id,
        )
        self.entries.append(entry)
        return entry

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
        matches = [entry for entry in self.entries if entry.workspace_id == workspace_id]
        if action:
            matches = [entry for entry in matches if entry.action == action]
        if actor_user_id:
            matches = [entry for entry in matches if entry.actor_user_id == actor_user_id]
        if since:
            matches = [entry for entry in matches if entry.created_at >= since]
        if until:
            matches = [entry for entry in matches if entry.created_at <= until]
        matches.sort(key=lambda entry: entry.created_at, reverse=True)
        if cursor:
            cursor_dt = datetime.fromisoformat(cursor)
            matches = [entry for entry in matches if entry.created_at < cursor_dt]
        return matches[:limit]


@dataclass
class FakeWorkspaceSettingsRepository:
    rows: dict[str, WorkspaceSettings] = field(default_factory=dict)

    async def get(self, workspace_id: str) -> WorkspaceSettings | None:
        return self.rows.get(workspace_id)

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
    ) -> WorkspaceSettings:
        settings = WorkspaceSettings(
            workspace_id=workspace_id,
            logo_url=logo_url,
            brand_color=brand_color,
            custom_domain=custom_domain,
            retention_days=retention_days,
            storage_limit_mb=storage_limit_mb,
            updated_at=datetime.now(UTC),
            updated_by_user_id=updated_by_user_id,
        )
        self.rows[workspace_id] = settings
        return settings


@dataclass
class FakeInvitationRepository:
    by_token: dict[str, Invitation] = field(default_factory=dict)

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
        invitation = Invitation(
            target_type=target_type,
            target_id=target_id,
            role=role,
            inviter_user_id=inviter_user_id,
            email=email,
            token=token,
            expires_at=expires_at,
            consumed_at=None,
            created_at=datetime.now(UTC),
        )
        self.by_token[token] = invitation
        return invitation

    async def get_by_token(self, token: str) -> Invitation | None:
        return self.by_token.get(token)

    async def consume(self, token: str) -> None:
        existing = self.by_token[token]
        self.by_token[token] = Invitation(
            target_type=existing.target_type,
            target_id=existing.target_id,
            role=existing.role,
            inviter_user_id=existing.inviter_user_id,
            email=existing.email,
            token=existing.token,
            expires_at=existing.expires_at,
            consumed_at=datetime.now(UTC),
            created_at=existing.created_at,
        )


@dataclass
class FakeUserLookupRepository:
    users: dict[str, UserSummary] = field(default_factory=dict)  # keyed by id

    async def get_by_email(self, email: str) -> UserSummary | None:
        return next(
            (user for user in self.users.values() if user.email.lower() == email.lower()), None
        )

    async def get_by_id(self, user_id: str) -> UserSummary | None:
        return self.users.get(user_id)


@dataclass
class FakeEmailSender:
    sent: list[dict[str, str]] = field(default_factory=list)

    async def send(self, *, to: str, subject: str, body: str) -> None:
        self.sent.append({"to": to, "subject": subject, "body": body})


@dataclass
class FakeResourcePermissionRepository:
    grants: dict[str, ResourcePermission] = field(default_factory=dict)

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
    ) -> ResourcePermission:
        key = (workspace_id, resource_type, resource_id, principal_type, principal_id, permission)
        existing = next(
            (
                (grant_id, grant)
                for grant_id, grant in self.grants.items()
                if (
                    grant.workspace_id,
                    grant.resource_type,
                    grant.resource_id,
                    grant.principal_type,
                    grant.principal_id,
                    grant.permission,
                )
                == key
            ),
            None,
        )
        if existing is not None:
            grant_id, old = existing
            updated = ResourcePermission(
                id=old.id,
                workspace_id=old.workspace_id,
                resource_type=old.resource_type,
                resource_id=old.resource_id,
                principal_type=old.principal_type,
                principal_id=old.principal_id,
                permission=old.permission,
                granted_by_user_id=granted_by_user_id,
                created_at=old.created_at,
            )
            self.grants[grant_id] = updated
            return updated

        grant = ResourcePermission(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
            principal_type=principal_type,
            principal_id=principal_id,
            permission=permission,
            granted_by_user_id=granted_by_user_id,
            created_at=datetime.now(UTC),
        )
        self.grants[grant.id] = grant
        return grant

    async def revoke_by_id(self, *, workspace_id: str, permission_id: str) -> None:
        existing = self.grants.get(permission_id)
        if existing is not None and existing.workspace_id == workspace_id:
            del self.grants[permission_id]

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
        return any(
            grant.workspace_id == workspace_id
            and grant.resource_type == resource_type
            and grant.resource_id == resource_id
            and grant.principal_type == principal_type
            and grant.principal_id == principal_id
            and grant.permission == permission
            for grant in self.grants.values()
        )

    async def list_for_workspace(self, workspace_id: str) -> list[ResourcePermission]:
        return [grant for grant in self.grants.values() if grant.workspace_id == workspace_id]


@dataclass
class FakeIpAllowlistRepository:
    entries: dict[str, IpAllowlistEntry] = field(default_factory=dict)

    async def list_for_workspace(self, workspace_id: str) -> list[IpAllowlistEntry]:
        return [e for e in self.entries.values() if e.workspace_id == workspace_id]

    async def add(
        self, *, workspace_id: str, cidr: str, label: str | None, created_by_user_id: str
    ) -> IpAllowlistEntry:
        entry = IpAllowlistEntry(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            cidr=cidr,
            label=label,
            created_by_user_id=created_by_user_id,
            created_at=datetime.now(UTC),
        )
        self.entries[entry.id] = entry
        return entry

    async def remove_by_id(self, *, workspace_id: str, entry_id: str) -> None:
        existing = self.entries.get(entry_id)
        if existing is not None and existing.workspace_id == workspace_id:
            del self.entries[entry_id]
