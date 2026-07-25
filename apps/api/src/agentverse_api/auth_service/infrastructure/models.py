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

from sqlalchemy import JSON, ForeignKey, Text, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentverse_api.auth_service.domain.role import Role
from agentverse_api.infrastructure.orm_base import Base


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
    value: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


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
    role: Mapped[Role] = mapped_column(
        SqlEnum(Role, name="workspace_role", values_callable=lambda enum: [e.value for e in enum])
    )
    created_at: Mapped[datetime]

    workspace: Mapped[Workspace] = relationship(back_populates="members")


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


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = _uuid_pk()
    # Nullable: pre-workspace events (e.g. raw signup) have no workspace yet.
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"), index=True, default=None
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
