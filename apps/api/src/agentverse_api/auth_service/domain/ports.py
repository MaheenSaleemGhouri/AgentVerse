"""Repository ports (Protocols). `infrastructure/repositories.py` implements
these against Postgres; `tests/` implements them against an in-memory
fake — application-layer use cases depend only on these interfaces
(CLAUDE.md §5: infrastructure implements domain-defined ports).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from agentverse_api.auth_service.domain.api_key_scope import ApiKeyScope
from agentverse_api.auth_service.domain.entities import (
    ApiKey,
    AuditLogEntry,
    CustomRole,
    Invitation,
    IpAllowlistEntry,
    MemberPresence,
    Organization,
    OrganizationMember,
    OrganizationSettings,
    OrganizationStats,
    OrganizationSummary,
    ResourcePermission,
    ScimToken,
    ScimUser,
    SecurityEvent,
    SsoConfiguration,
    TrustedDevice,
    UserSummary,
    Workspace,
    WorkspaceMember,
    WorkspaceSettings,
    WorkspaceSummary,
)
from agentverse_api.auth_service.domain.invitation_target_type import InvitationTargetType
from agentverse_api.auth_service.domain.permission import Permission
from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.domain.security import (
    PasswordPolicy,
    SecurityEventType,
    SecuritySeverity,
)
from agentverse_api.auth_service.domain.sso import SsoPreset, SsoProtocol


class WorkspaceRepository(Protocol):
    async def create_workspace(self, *, name: str, slug: str, owner_user_id: str) -> Workspace: ...

    async def get_workspace(self, workspace_id: str) -> Workspace | None: ...

    async def list_for_user(self, user_id: str) -> list[WorkspaceSummary]: ...

    async def slug_exists(self, slug: str) -> bool: ...

    async def get_membership(
        self, *, workspace_id: str, user_id: str
    ) -> WorkspaceMember | None: ...

    async def add_member(
        self, *, workspace_id: str, user_id: str, role: Role
    ) -> WorkspaceMember: ...

    async def update_member_role(
        self, *, workspace_id: str, user_id: str, role: Role
    ) -> WorkspaceMember: ...

    async def remove_member(self, *, workspace_id: str, user_id: str) -> None: ...

    async def count_owners(self, workspace_id: str) -> int: ...

    async def list_members(self, workspace_id: str) -> list[WorkspaceMember]: ...

    async def count_two_factor_coverage(self, workspace_id: str) -> tuple[int, int]:
        """`(members with two-factor enabled, total members)`.

        Returned as a pair from one query rather than two calls, so the
        ratio can never be computed from two different points in time.
        """
        ...


class WorkspaceSettingsRepository(Protocol):
    async def get(self, workspace_id: str) -> WorkspaceSettings | None: ...

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
    ) -> WorkspaceSettings: ...


class OrganizationSettingsRepository(Protocol):
    async def get(self, organization_id: str) -> OrganizationSettings | None: ...

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
    ) -> OrganizationSettings: ...


class SecurityEventRepository(Protocol):
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
    ) -> SecurityEvent: ...

    async def list_for_user(
        self,
        user_id: str,
        *,
        limit: int,
        severity: SecuritySeverity | None = None,
    ) -> list[SecurityEvent]: ...

    async def list_for_workspace(
        self,
        workspace_id: str,
        *,
        limit: int,
        severity: SecuritySeverity | None = None,
    ) -> list[SecurityEvent]: ...

    async def count_critical_since(self, workspace_id: str, *, since: datetime) -> int: ...

    async def count_recent_failures(self, *, user_id: str, since: datetime) -> int: ...


class TrustedDeviceRepository(Protocol):
    async def upsert(
        self,
        *,
        user_id: str,
        device_fingerprint: str,
        device_name: str | None,
        user_agent: str | None,
        ip_address: str | None,
    ) -> TrustedDevice: ...

    async def get(self, *, user_id: str, device_fingerprint: str) -> TrustedDevice | None: ...

    async def list_for_user(self, user_id: str) -> list[TrustedDevice]: ...

    async def revoke(self, *, user_id: str, device_id: str) -> TrustedDevice | None: ...


class PasswordPolicyRepository(Protocol):
    async def get(self, organization_id: str) -> PasswordPolicy | None: ...

    async def upsert(
        self,
        *,
        organization_id: str,
        policy: PasswordPolicy,
        updated_by_user_id: str,
    ) -> PasswordPolicy: ...


class ApiKeyRepository(Protocol):
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
    ) -> ApiKey: ...

    async def list_api_keys(self, workspace_id: str) -> list[ApiKey]: ...

    async def count_non_expiring(self, workspace_id: str) -> int:
        """Active keys with no expiry — an input to the security score."""
        ...

    async def get_api_key(self, api_key_id: str) -> ApiKey | None: ...

    async def revoke_api_key(self, api_key_id: str) -> None: ...

    async def find_active_by_hash(self, hashed_key: str) -> ApiKey | None:
        """Looks a key up by its hash for bearer authentication.

        Returns `None` for a revoked key as well as an unknown one — the
        caller must not be able to tell a revoked credential from one
        that never existed.
        """
        ...

    async def touch_last_used(self, api_key_id: str) -> None:
        """Records that the key just authenticated a request, bumping
        `last_used_at` and `use_count`. Best-effort telemetry for the
        key-management UI, never an authorization input.
        """
        ...


class OrganizationRepository(Protocol):
    async def create_organization(
        self, *, name: str, slug: str, owner_user_id: str
    ) -> Organization: ...

    async def get_organization(self, organization_id: str) -> Organization | None: ...

    async def list_for_user(self, user_id: str) -> list[OrganizationSummary]: ...

    async def slug_exists(self, slug: str) -> bool: ...

    async def rename_organization(self, *, organization_id: str, name: str) -> Organization: ...

    async def delete_organization(self, organization_id: str) -> None: ...

    async def get_membership(
        self, *, organization_id: str, user_id: str
    ) -> OrganizationMember | None: ...

    async def add_member(
        self, *, organization_id: str, user_id: str, role: Role
    ) -> OrganizationMember: ...

    async def update_member_role(
        self, *, organization_id: str, user_id: str, role: Role
    ) -> OrganizationMember: ...

    async def suspend_member(self, *, organization_id: str, user_id: str) -> OrganizationMember: ...

    async def reinstate_member(
        self, *, organization_id: str, user_id: str
    ) -> OrganizationMember: ...

    async def remove_member(self, *, organization_id: str, user_id: str) -> None: ...

    async def count_owners(self, organization_id: str) -> int: ...

    async def list_members(self, organization_id: str) -> list[OrganizationMember]: ...

    async def list_workspaces(self, organization_id: str) -> list[Workspace]: ...

    async def list_member_presence(self, organization_id: str) -> list[MemberPresence]:
        """Members with their session-derived activity.

        One query joining sessions rather than N per member: a 500-person
        organization would otherwise issue 500 round trips to render one
        page.
        """
        ...

    async def stats(self, organization_id: str) -> OrganizationStats: ...

    async def attach_workspace(self, *, organization_id: str, workspace_id: str) -> None: ...

    async def detach_workspace(self, *, workspace_id: str) -> None: ...


class InvitationRepository(Protocol):
    """Stores/reads invitation rows in Better Auth's `verifications`
    table (ADR-0005: apps/api-domain use of a Better-Auth-owned table,
    via Alembic) — never Better Auth's own reset-password/email-verify
    rows, which this repository never touches.
    """

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
    ) -> Invitation: ...

    async def get_by_token(self, token: str) -> Invitation | None: ...

    async def consume(self, token: str) -> None: ...


class UserLookupRepository(Protocol):
    async def get_by_email(self, email: str) -> UserSummary | None: ...

    async def get_by_id(self, user_id: str) -> UserSummary | None: ...


class EmailSender(Protocol):
    """Provider-abstraction boundary for transactional email (CLAUDE.md
    §9) — no caller imports a vendor SDK directly. The only
    implementation today (`LoggingEmailSender`) logs instead of
    delivering; swapping in a real vendor is a new class behind this
    same Protocol.
    """

    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class ResourcePermissionRepository(Protocol):
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
        """Idempotent: granting an already-granted tuple updates
        `granted_by_user_id` and returns the existing row rather than
        erroring or duplicating it (the full six-column tuple is unique).
        """
        ...

    async def revoke_by_id(self, *, workspace_id: str, permission_id: str) -> None: ...

    async def check(
        self,
        *,
        workspace_id: str,
        resource_type: str,
        resource_id: str,
        principal_type: str,
        principal_id: str,
        permission: str,
    ) -> bool: ...

    async def list_for_workspace(self, workspace_id: str) -> list[ResourcePermission]: ...


class CustomRoleRepository(Protocol):
    """Tenant-defined roles. Every method is `workspace_id`-scoped: a role
    is a tenant's own vocabulary, and an unscoped lookup here would be a
    cross-tenant read on a Rule 11 model.
    """

    async def create(
        self,
        *,
        workspace_id: str,
        name: str,
        description: str | None,
        base_role: Role,
        permissions: list[str],
        created_by_user_id: str,
    ) -> CustomRole: ...

    async def update(
        self,
        *,
        workspace_id: str,
        role_id: str,
        name: str | None,
        description: str | None,
        base_role: Role | None,
        permissions: list[str] | None,
    ) -> CustomRole:
        """Raises `CustomRoleNotFoundError` when the role belongs to
        another workspace, rather than reporting a distinguishable
        \"exists but not yours\" — same non-leaking contract the rest of
        this layer holds to.
        """
        ...

    async def delete(self, *, workspace_id: str, role_id: str) -> None: ...

    async def get(self, *, workspace_id: str, role_id: str) -> CustomRole | None: ...

    async def list_for_workspace(self, workspace_id: str) -> list[CustomRole]: ...

    async def list_permissions(self, *, workspace_id: str, role_id: str) -> frozenset[Permission]:
        """The role's additive grants, or an empty set if it does not
        belong to this workspace. Returns empty rather than raising
        because this sits on the authorization hot path — a missing role
        must fail closed, not 500.
        """
        ...


class IpAllowlistRepository(Protocol):
    async def list_for_workspace(self, workspace_id: str) -> list[IpAllowlistEntry]: ...

    async def add(
        self, *, workspace_id: str, cidr: str, label: str | None, created_by_user_id: str
    ) -> IpAllowlistEntry: ...

    async def remove_by_id(self, *, workspace_id: str, entry_id: str) -> None: ...


class SsoConfigurationRepository(Protocol):
    async def list_for_organization(self, organization_id: str) -> list[SsoConfiguration]: ...

    async def get(self, *, organization_id: str, config_id: str) -> SsoConfiguration | None: ...

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
    ) -> SsoConfiguration:
        """Creates or replaces the config for `(organization, protocol)`.

        `sealed_secret` is `(ciphertext, wrapped_dek, key_version)` or
        `None` to leave an existing secret untouched — so an admin can
        edit the issuer URL without re-entering the secret.
        """
        ...

    async def delete(self, *, organization_id: str, config_id: str) -> None: ...

    async def list_enabled_sealed(
        self, protocol: SsoProtocol
    ) -> list[tuple[SsoConfiguration, tuple[bytes, bytes, str] | None]]:
        """Every *enabled* config for `protocol`, paired with its sealed
        secret. The only read path that surfaces the sealed bytes at all —
        used solely by the internal provider-resolution endpoint, never by
        anything reachable from a browser.
        """
        ...


class ScimTokenRepository(Protocol):
    async def create(
        self,
        *,
        organization_id: str,
        name: str,
        token_prefix: str,
        hashed_token: str,
        created_by_user_id: str,
    ) -> ScimToken: ...

    async def list_for_organization(self, organization_id: str) -> list[ScimToken]: ...

    async def find_active_by_hash(self, hashed_token: str) -> ScimToken | None:
        """Returns `None` for a revoked token as well as an unknown one —
        an IdP probing tokens must not be able to tell them apart.
        """
        ...

    async def touch_last_used(self, token_id: str) -> None: ...

    async def revoke(self, *, organization_id: str, token_id: str) -> bool:
        """`False` when the token does not exist *or* belongs to another
        organization — the caller cannot distinguish the two (Rule 11).
        """
        ...


class ScimRepository(Protocol):
    """Reads and writes the `users` + `organization_members` pair that
    SCIM provisions. Separate from `OrganizationRepository` because SCIM
    is the one caller that also creates the `users` row (see
    `application/scim_service.py` for why that is permitted).
    """

    async def list_users(
        self, *, organization_id: str, email: str | None, start_index: int, count: int
    ) -> tuple[list[ScimUser], int]:
        """Returns `(page, total_matching)` — SCIM's `ListResponse`
        requires the unpaged total, not just the page length.
        """
        ...

    async def get_user(self, *, organization_id: str, user_id: str) -> ScimUser | None: ...

    async def create_user(
        self, *, organization_id: str, email: str, display_name: str, role: Role
    ) -> ScimUser:
        """Creates the account if the email is new, then the membership.
        An email that already has an account is linked, never duplicated.
        """
        ...

    async def set_active(
        self, *, organization_id: str, user_id: str, active: bool
    ) -> ScimUser | None: ...

    async def set_display_name(
        self, *, organization_id: str, user_id: str, display_name: str
    ) -> ScimUser | None: ...

    async def remove_user(self, *, organization_id: str, user_id: str) -> bool: ...

    async def list_groups(self, organization_id: str) -> list[Workspace]: ...

    async def get_group(self, *, organization_id: str, workspace_id: str) -> Workspace | None: ...


class AuditLogRepository(Protocol):
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
    ) -> AuditLogEntry: ...

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
    ) -> list[AuditLogEntry]: ...

    async def count_by_day(self, workspace_id: str, *, since: datetime) -> list[tuple[date, int]]:
        """Daily entry counts, oldest first, for the activity graph.

        Aggregated in SQL rather than by counting fetched rows: a busy
        workspace's 30-day history is far larger than the graph needs,
        and pulling it all back to count it in Python would be the
        expensive way to draw a small chart.
        """
        ...
