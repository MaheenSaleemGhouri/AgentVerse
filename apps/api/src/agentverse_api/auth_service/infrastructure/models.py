"""SQLAlchemy ORM models.

`User`/`Session`/`Account`/`Verification` mirror Better Auth's default
schema (ADR-0005) — column names are snake_case per `CLAUDE.md` §8, and
`apps/web/lib/auth.ts`'s `fields` mapping must match these exactly.
`Workspace`/`WorkspaceMember`/`ApiKey`/`AuditLog` are this platform's
own domain, owned by `apps/api`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, LargeBinary, Text, TypeDecorator, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentverse_api.auth_service.domain.role import Role
from agentverse_api.infrastructure.orm_base import Base


class RoleType(TypeDecorator[Role]):
    """TEXT in the database, `Role` in Python.

    The role columns moved off the `workspace_role` Postgres ENUM so the
    seven-tier model could stay reversible (migration `b3f7c1a9e582`).
    A bare `Text` column would have made `Mapped[Role]` a lie — SQLAlchemy
    would hand back plain strings, and `role is Role.OWNER` identity
    checks would quietly start failing while `==` kept working, which is
    exactly the kind of half-broken that survives a test suite.

    Coercing here rather than in each `_to_*` converter keeps it in one
    place: every read goes through this, so no future converter can
    forget.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Role | str | None, dialect: object) -> str | None:
        if value is None:
            return None
        return Role(value).value

    def process_result_value(self, value: str | None, dialect: object) -> Role | None:
        if value is None:
            return None
        return Role(value)


def _uuid_pk() -> Mapped[str]:
    return mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Better Auth-owned tables (ADR-0005) — schema fixed by Better Auth's
# defaults, translated to snake_case. Alembic authors these; Better Auth
# only reads/writes through the `fields` mapping in apps/web/lib/auth.ts.
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text, unique=True, index=True)
    email_verified: Mapped[bool] = mapped_column(default=False)
    image: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(index=True)
    updated_at: Mapped[datetime]
    # Better Auth's `twoFactor()` plugin adds this to its `user` model
    # (Increment 7.2) — Alembic authors it, same as every other Better
    # Auth-owned column (ADR-0005).
    two_factor_enabled: Mapped[bool] = mapped_column(default=False)
    # apps/web-owned account locking (Increment 7.5), enforced inside the
    # already-customized `password.verify` override in
    # `apps/web/lib/password-hashing.ts` — the same extension point
    # ADR-0005 used for Argon2id. Not a Better Auth field.
    failed_login_count: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(default=None)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime]
    ip_address: Mapped[str | None] = mapped_column(Text, default=None)
    user_agent: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(Text)
    provider_id: Mapped[str] = mapped_column(Text)
    access_token: Mapped[str | None] = mapped_column(Text, default=None)
    refresh_token: Mapped[str | None] = mapped_column(Text, default=None)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(default=None)
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(default=None)
    scope: Mapped[str | None] = mapped_column(Text, default=None)
    id_token: Mapped[str | None] = mapped_column(Text, default=None)
    # Argon2id hash (ADR-0005) for credential ("credential" provider_id)
    # accounts only; null for OAuth-only accounts.
    password: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    identifier: Mapped[str] = mapped_column(Text, index=True)
    value: Mapped[str] = mapped_column(Text, index=True)
    expires_at: Mapped[datetime]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    # apps/api-only (Increment 5): enforces invitation tokens are
    # single-use. Better Auth's own rows (reset-password, email
    # verification) never populate this — it manages their lifecycle
    # itself and is never queried by anything that reads this column.
    consumed_at: Mapped[datetime | None] = mapped_column(default=None)


class TwoFactor(Base):
    """Better Auth's `twoFactor()` plugin table (Increment 7.2), authored
    by Alembic in snake_case — the same precedent `jwks` set: the plugin
    documents its schema, we create it, and `apps/web/lib/auth.ts`'s
    `schema.twoFactor.fields` mapping points at these exact columns.

    `secret`/`backup_codes` are Better Auth-encrypted at rest (it never
    returns them over the API — `returned: false` in its own schema).
    """

    __tablename__ = "two_factor"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    secret: Mapped[str] = mapped_column(Text, index=True)
    backup_codes: Mapped[str] = mapped_column(Text)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    verified: Mapped[bool] = mapped_column(default=True)
    failed_verification_count: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(default=None)


class Jwk(Base):
    """Better Auth's JWT plugin signing keypair (ADR-0005) — not part of
    the plugin's documented default schema list until you actually
    enable `jwt()`; missing this table surfaces as a 500 only when a
    client first requests `/api/auth/token`, which is exactly how this
    was caught (a real request, not a doc read).
    """

    __tablename__ = "jwks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    public_key: Mapped[str] = mapped_column(Text)
    private_key: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime | None] = mapped_column(default=None)


# ---------------------------------------------------------------------------
# apps/api-owned domain tables (workspace/RBAC — ADR-0004)
# ---------------------------------------------------------------------------


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, unique=True, index=True)
    created_at: Mapped[datetime]
    # Nullable, `ON DELETE SET NULL`: an organization groups workspaces for
    # billing/SSO/branding only (ADR-0011) — it is never the isolation
    # boundary, so deleting the organization detaches, never deletes, the
    # workspace.
    organization_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        index=True,
        default=None,
    )

    members: Mapped[list[WorkspaceMember]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),)

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # TEXT, not a Postgres ENUM: the seven-tier role model has to stay
    # reversible, and enum values cannot be dropped (see migration
    # `b3f7c1a9e582`). `Role` still validates every value at the domain
    # boundary, and a CHECK constraint holds the line in the database.
    role: Mapped[Role] = mapped_column(RoleType)
    #: Set when the member holds a tenant-defined role instead of a
    #: built-in one. `role` still carries the custom role's base tier, so
    #: every pre-existing `require_role` check keeps working unchanged.
    custom_role_id: Mapped[str | None] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"), default=None, index=True
    )
    created_at: Mapped[datetime]

    workspace: Mapped[Workspace] = relationship(back_populates="members")


class Organization(Base):
    """Additive grouping layer over `workspaces` (ADR-0011) — never an
    isolation boundary. `workspace_members` remains the sole source of
    workspace authorization regardless of organization membership.
    """

    __tablename__ = "organizations"

    id: Mapped[str] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, unique=True, index=True)
    created_at: Mapped[datetime]


class OrganizationMember(Base):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_organization_member"),
    )

    id: Mapped[str] = _uuid_pk()
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Same TEXT + CHECK treatment as `workspace_members.role`, and for the
    # same reversibility reason — the two columns shared the one enum type
    # and had to move off it together (migration `b3f7c1a9e582`).
    role: Mapped[Role] = mapped_column(RoleType)
    # Mirrors `ApiKey.revoked_at`: suspending keeps the row (audit-followable)
    # instead of deleting it. `None` means active.
    suspended_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime]


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    key_prefix: Mapped[str] = mapped_column(Text)
    hashed_key: Mapped[str] = mapped_column(Text, unique=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime]
    last_used_at: Mapped[datetime | None] = mapped_column(default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)
    # Plain TEXT, not a Postgres ENUM: `ApiKeyScope` is app-validated at
    # the Pydantic boundary, and a TEXT column never needs a migration to
    # add a new allowed value (an ENUM's values aren't cleanly reversible
    # to drop, the same reasoning the `protocol_config` design elsewhere
    # in this codebase already applies).
    scope: Mapped[str] = mapped_column(Text, server_default="full")
    tier: Mapped[str] = mapped_column(Text, server_default="standard")
    rotated_from_id: Mapped[str | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL"), default=None
    )
    #: `None` means the key never expires. Enforced in the bearer path,
    #: not merely displayed — a stored expiry that nothing checks is
    #: worse than none, because it reads as a control that isn't there.
    expires_at: Mapped[datetime | None] = mapped_column(default=None)
    #: Incremented on every successful authentication, alongside
    #: `last_used_at`. A count answers "is this key still in use and how
    #: heavily", which a single timestamp cannot.
    use_count: Mapped[int] = mapped_column(server_default="0", default=0)
    #: `ApiKeyKind` — what surface this credential authenticates against
    #: (`/api/v1/*` vs `/mcp`, Phase 12/ADR-0017). Plain TEXT for the
    #: same reason `scope` above is: app-validated, no ENUM migration
    #: needed to add a future kind.
    kind: Mapped[str] = mapped_column(Text, server_default="user_api_key")


class WorkspaceSettings(Base):
    """1:1 with `Workspace` — `workspace_id` is both the primary key and
    the foreign key, so a workspace can have at most one settings row and
    a `get_or_default` read (no row yet) is a real, expected state rather
    than an integrity concern.
    """

    __tablename__ = "workspace_settings"

    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    logo_url: Mapped[str | None] = mapped_column(Text, default=None)
    brand_color: Mapped[str | None] = mapped_column(Text, default=None)
    custom_domain: Mapped[str | None] = mapped_column(Text, unique=True, default=None)
    retention_days: Mapped[int | None] = mapped_column(default=None)
    storage_limit_mb: Mapped[int | None] = mapped_column(default=None)
    updated_at: Mapped[datetime]
    updated_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )


class OrganizationSettings(Base):
    """1:1 with `Organization`, same shape as `WorkspaceSettings` — the
    id is both PK and FK, so "no row yet" is the documented default state
    rather than a missing-record error.
    """

    __tablename__ = "organization_settings"

    organization_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    logo_url: Mapped[str | None] = mapped_column(Text, default=None)
    brand_color: Mapped[str | None] = mapped_column(Text, default=None)
    # Unique across organizations for the same reason it is unique across
    # workspaces: a custom domain resolves to exactly one tenant.
    custom_domain: Mapped[str | None] = mapped_column(Text, unique=True, default=None)
    website_url: Mapped[str | None] = mapped_column(Text, default=None)
    support_email: Mapped[str | None] = mapped_column(Text, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    updated_at: Mapped[datetime]
    updated_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )


class SecurityEvent(Base):
    """Security signals about an identity — see
    `domain.security.SecurityEventType` for why this is not `audit_logs`.

    Every scoping column is nullable because the events that matter most
    arrive before scope is known: a failed login has no workspace, and
    often no user.
    """

    __tablename__ = "security_events"

    id: Mapped[str] = _uuid_pk()
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, default=None
    )
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"), index=True, default=None
    )
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, default=None
    )
    event_type: Mapped[str] = mapped_column(Text, index=True)
    severity: Mapped[str] = mapped_column(Text, index=True)
    ip_address: Mapped[str | None] = mapped_column(Text, default=None)
    user_agent: Mapped[str | None] = mapped_column(Text, default=None)
    event_metadata: Mapped[dict[str, str]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(index=True)


class TrustedDevice(Base):
    """A device a user has confirmed. Unique per (user, fingerprint) so
    re-confirming an already-trusted device updates it instead of
    accumulating duplicate rows.
    """

    __tablename__ = "trusted_devices"
    __table_args__ = (UniqueConstraint("user_id", "device_fingerprint"),)

    id: Mapped[str] = _uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    device_fingerprint: Mapped[str] = mapped_column(Text)
    device_name: Mapped[str | None] = mapped_column(Text, default=None)
    user_agent: Mapped[str | None] = mapped_column(Text, default=None)
    ip_address: Mapped[str | None] = mapped_column(Text, default=None)
    trusted_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)


class PasswordPolicy(Base):
    """1:1 with `Organization`. No row means the platform default
    (`domain.security.DEFAULT_PASSWORD_POLICY`) applies — the default is
    a real baseline, not "no rules".
    """

    __tablename__ = "password_policies"

    organization_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    min_length: Mapped[int]
    require_uppercase: Mapped[bool]
    require_lowercase: Mapped[bool]
    require_number: Mapped[bool]
    require_symbol: Mapped[bool]
    max_age_days: Mapped[int | None] = mapped_column(default=None)
    updated_at: Mapped[datetime]
    updated_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = _uuid_pk()
    # Nullable: pre-workspace events (e.g. raw signup) have no workspace yet.
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"), index=True, default=None
    )
    # Nullable: set only for organization-level events (e.g.
    # `organization.created`) that have no single workspace to attribute to.
    organization_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        index=True,
        default=None,
    )
    # Nullable: system-initiated entries have no human actor.
    actor_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    action: Mapped[str] = mapped_column(Text, index=True)
    target: Mapped[str | None] = mapped_column(Text, default=None)
    outcome: Mapped[str] = mapped_column(Text)
    # Python attribute is `log_metadata` (DeclarativeBase already reserves
    # `.metadata` for the class-level MetaData object) but the DB column
    # is named `metadata`, matching the domain entity field name.
    log_metadata: Mapped[dict[str, str]] = mapped_column(
        "metadata", JSONB().with_variant(JSON, "sqlite")
    )
    created_at: Mapped[datetime] = mapped_column(index=True)


class WorkspaceIpAllowlist(Base):
    """Opt-in per-workspace IP restriction (Increment 7.4).

    Empty = unrestricted, which is why every pre-existing workspace is
    unaffected by default: the enforcing dependency treats "no rows" as
    "allow everything" rather than "deny everything". Fail-open is
    correct *here specifically* — an empty allowlist means the feature
    was never configured, not that access was revoked.
    """

    __tablename__ = "workspace_ip_allowlist"
    __table_args__ = (
        UniqueConstraint("workspace_id", "cidr", name="uq_workspace_ip_allowlist_cidr"),
    )

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    #: Stored as TEXT, validated as an IPv4/IPv6 network by the
    #: application layer — Postgres has a native `cidr` type, but the
    #: value has to round-trip through Python's `ipaddress` module for
    #: the match check anyway, so TEXT keeps one validation path.
    cidr: Mapped[str] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(Text, default=None)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime]


class SsoConfiguration(Base):
    """Org-scoped SSO configuration (Increment 8). See migration
    `f4b8d1e6c037` for why `protocol`/`preset` are TEXT and
    `protocol_config` is JSONB.

    The client secret is sealed with the existing `CredentialVault`
    envelope (never plaintext, never logged) — the three columns below
    mirror the MCP integration-credential shape exactly.
    """

    __tablename__ = "sso_configurations"

    id: Mapped[str] = _uuid_pk()
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    protocol: Mapped[str] = mapped_column(Text)
    preset: Mapped[str] = mapped_column(Text, server_default="generic")
    issuer_url: Mapped[str | None] = mapped_column(Text, default=None)
    client_id: Mapped[str | None] = mapped_column(Text, default=None)
    client_secret_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)
    wrapped_dek: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)
    key_version: Mapped[str | None] = mapped_column(Text, default=None)
    protocol_config: Mapped[dict[str, str]] = mapped_column(JSONB().with_variant(JSON, "sqlite"))
    enabled: Mapped[bool] = mapped_column(default=False)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class ScimToken(Base):
    """Bearer credential an identity provider presents to the SCIM 2.0
    endpoints. Organization-scoped, and deliberately not an `api_keys`
    row — see the migration for why.
    """

    __tablename__ = "scim_tokens"

    id: Mapped[str] = _uuid_pk()
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    token_prefix: Mapped[str] = mapped_column(Text)
    hashed_token: Mapped[str] = mapped_column(Text, unique=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime]
    last_used_at: Mapped[datetime | None] = mapped_column(default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)


class ResourcePermission(Base):
    """An orthogonal grant on top of the four base workspace roles
    (Increment 6) — see the domain entity's docstring for why this exists
    instead of widening `workspace_role`.
    """

    __tablename__ = "resource_permissions"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "resource_type",
            "resource_id",
            "principal_type",
            "principal_id",
            "permission",
            name="uq_resource_permission",
        ),
    )

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    resource_type: Mapped[str] = mapped_column(Text)
    resource_id: Mapped[str] = mapped_column(Text, server_default="")
    principal_type: Mapped[str] = mapped_column(Text, server_default="user")
    principal_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    permission: Mapped[str] = mapped_column(Text)
    granted_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime]


class CustomRole(Base):
    """A tenant-defined role, always anchored to a built-in base tier.

    Workspace-scoped rather than global: a role name is a tenant's own
    vocabulary, and a shared role table would be a cross-tenant surface
    on a model where `workspace_id` isolation is absolute (Rule 11).
    """

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_role_workspace_name"),)

    id: Mapped[str] = _uuid_pk()
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    #: The built-in tier this role inherits from. Keeps a custom role
    #: rankable, so routes gated on a minimum role need no awareness of
    #: custom roles at all.
    base_role: Mapped[Role] = mapped_column(RoleType)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime | None] = mapped_column(default=None)


class CustomRolePermission(Base):
    """One additive grant on a custom role.

    Additive only — there is deliberately no "deny" flag. A role that
    subtracted an inherited capability would make the hierarchy
    non-monotonic and silently break every route still gated on a
    minimum role.
    """

    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission", name="uq_role_permission"),)

    id: Mapped[str] = _uuid_pk()
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), index=True)
    permission: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime]


class PlatformAdmin(Base):
    """A user who acts for AgentVerse itself rather than for a workspace.

    A genuinely new kind of authority, and deliberately the narrowest one
    that works. Every other permission in this platform answers "what may
    this identity do *inside this workspace*" — but moderating the
    marketplace is a judgement about a listing that belongs to someone
    else's workspace, so no workspace role can express it. Routing it
    through `require_role` instead would have let a publisher approve
    themselves.

    There is no grant route, on purpose. Membership is granted out of
    band (a migration or an operator's INSERT) and every use is
    audit-logged, so the set of people who can approve a public listing
    changes only through a reviewed, recorded action — not through an
    endpoint that becomes a privilege-escalation target the moment one
    admin account is compromised.

    Global by design, so no `workspace_id`: it is one of the explicit
    exemptions from Rule 11, alongside `users` and platform feature
    flags.
    """

    __tablename__ = "platform_admins"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    #: Why this person has it. Read during an incident review, when
    #: "who could have approved this listing, and why did they have that
    #: power" is the question being asked.
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime]
