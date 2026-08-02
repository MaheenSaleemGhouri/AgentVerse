"""Workspace/RBAC domain entities — plain dataclasses, no ORM/framework coupling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from agentverse_api.auth_service.domain.api_key_scope import ApiKeyScope
from agentverse_api.auth_service.domain.invitation_target_type import InvitationTargetType
from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.domain.sso import SsoPreset, SsoProtocol


@dataclass(frozen=True, slots=True)
class Workspace:
    id: str
    name: str
    slug: str
    created_at: datetime
    #: The organization this workspace is grouped under, if any. Purely
    #: additive metadata — it grants no implicit access; `workspace_members`
    #: remains the sole source of workspace authorization (ADR-0006).
    organization_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceMember:
    workspace_id: str
    user_id: str
    role: Role
    created_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceSummary:
    """A workspace plus the calling user's role in it — the workspace
    switcher's list view. Distinct from `Workspace` (no implicit role)
    so a workspace fetched without a resolved caller can't accidentally
    be treated as if it carried role information.
    """

    workspace: Workspace
    role: Role


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    """Resolved by `get_current_workspace` — the only trusted answer to
    "does this identity have access to this workspace, and at what role."
    """

    workspace_id: str
    user_id: str
    role: Role
    #: Set when the request authenticated with an API key rather than a
    #: user session. `user_id` is then the key's issuer and `role` is
    #: already the scope-capped effective role, so every downstream
    #: permission check is unchanged — this exists so audit entries can
    #: say *which credential* acted, not to gate anything.
    api_key_id: str | None = None


@dataclass(frozen=True, slots=True)
class ApiKey:
    id: str
    workspace_id: str
    name: str
    key_prefix: str
    hashed_key: str
    created_by_user_id: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    scope: ApiKeyScope
    tier: str
    #: Set when this key was created by rotating another — the id of the
    #: key it replaced, forming an audit-followable chain. `None` for a
    #: key issued directly, including every key that existed before
    #: rotation shipped.
    rotated_from_id: str | None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


@dataclass(frozen=True, slots=True)
class WorkspaceSettings:
    """Workspace-wide branding/policy — distinct from `settings/appearance`,
    which is a *personal* light/dark/system theme toggle stored client-side.

    `retention_days`/`storage_limit_mb` are policy only: no worker job
    purges data on `retention_days` and no upload path checks
    `storage_limit_mb` yet. Storing the value the admin configured is a
    real, useful capability on its own (and the prerequisite for
    enforcement); claiming enforcement that doesn't exist is not.
    """

    workspace_id: str
    logo_url: str | None
    brand_color: str | None
    custom_domain: str | None
    retention_days: int | None
    storage_limit_mb: int | None
    updated_at: datetime
    updated_by_user_id: str | None


@dataclass(frozen=True, slots=True)
class AuditLogEntry:
    id: str
    workspace_id: str | None
    actor_user_id: str | None
    action: str
    target: str | None
    outcome: str
    metadata: dict[str, str]
    created_at: datetime
    #: Set for organization-level events (e.g. `organization.created`)
    #: that have no single workspace to attribute to. `None` for every
    #: pre-existing entry and every workspace-scoped one.
    organization_id: str | None = None


@dataclass(frozen=True, slots=True)
class Organization:
    id: str
    name: str
    slug: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class OrganizationMember:
    organization_id: str
    user_id: str
    role: Role
    created_at: datetime
    #: Mirrors `ApiKey.revoked_at` — a suspended member keeps their row
    #: (audit-followable) instead of being deleted. `None` means active.
    suspended_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ScimToken:
    """Bearer credential an identity provider presents to the SCIM
    endpoints, scoped to exactly one organization.
    """

    id: str
    organization_id: str
    name: str
    token_prefix: str
    created_by_user_id: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


@dataclass(frozen=True, slots=True)
class ScimUser:
    """One provisioned identity, as SCIM sees it: the `users` row joined
    to its organization membership. `active` is the membership's
    suspension state — SCIM's deactivate maps to suspending the member,
    never to deleting the account.
    """

    user_id: str
    email: str
    display_name: str
    role: Role
    active: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class OrganizationSummary:
    """An organization plus the calling user's role in it — parallels
    `WorkspaceSummary` for the same reason (no implicit role on a bare
    `Organization` fetched without a resolved caller).
    """

    organization: Organization
    role: Role


@dataclass(frozen=True, slots=True)
class OrganizationContext:
    """Resolved by `get_current_organization` — the only trusted answer to
    "does this identity have access to this organization, and at what role."
    Structurally identical to `WorkspaceContext` by design (ADR-0006): the
    two are deliberately parallel, never merged into one context type,
    because organization access and workspace access are independent.
    """

    organization_id: str
    user_id: str
    role: Role


@dataclass(frozen=True, slots=True)
class UserSummary:
    """Minimal read access to `users` — apps/api does not own user
    creation/auth (Better Auth does, ADR-0005); this exists only to
    resolve an email to an account id for the invite/accept flow.
    """

    id: str
    email: str


@dataclass(frozen=True, slots=True)
class Invitation:
    target_type: InvitationTargetType
    target_id: str
    role: Role
    #: Preserved through the token so the audit trail correctly credits
    #: whoever actually sent the invite, not whoever eventually accepts it
    #: (acceptance can happen days later, by which point "the actor" would
    #: otherwise be lost).
    inviter_user_id: str
    email: str
    token: str
    expires_at: datetime
    consumed_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ResourcePermission:
    """An orthogonal grant layered on top of the four base workspace roles
    (ADR-consistent with `require_role`'s own design note: the role
    hierarchy never grows past four values — Postgres ENUM values aren't
    cleanly reversible to drop). A `member` can hold `resource_type
    "billing", permission "manage"` without their role floor changing at
    all; `require_resource_permission` composes *alongside*
    `require_role`, never replacing it.
    """

    id: str
    workspace_id: str
    resource_type: str
    #: `""` means the grant applies to every resource of `resource_type`
    #: in the workspace (e.g. `billing`, which has no individual
    #: instances) rather than one specific instance.
    resource_id: str
    #: Always `"user"` today — kept as its own column, not folded into
    #: `principal_id`, so a future group/role principal type is a new
    #: value here, not a schema change.
    principal_type: str
    principal_id: str
    permission: str
    granted_by_user_id: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class IpAllowlistEntry:
    """One allowed CIDR range for a workspace (Increment 7.4). A
    workspace with zero entries is unrestricted — see
    `infrastructure.models.WorkspaceIpAllowlist` for why that fail-open
    is deliberate here.
    """

    id: str
    workspace_id: str
    cidr: str
    label: str | None
    created_by_user_id: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SsoConfiguration:
    """Org-scoped SSO config (Increment 8).

    The client secret is **never** on this entity — it lives sealed in
    the database and is opened only at the point of use. An entity that
    carried it would end up in a log line or an API response eventually.
    """

    id: str
    organization_id: str
    protocol: SsoProtocol
    preset: SsoPreset
    issuer_url: str | None
    client_id: str | None
    #: True when a sealed client secret exists — lets the UI show
    #: "configured" without the value ever leaving the database.
    has_client_secret: bool
    protocol_config: dict[str, str]
    enabled: bool
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime
