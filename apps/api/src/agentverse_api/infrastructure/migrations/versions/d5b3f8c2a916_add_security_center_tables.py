"""add security center tables

Revision ID: d5b3f8c2a916
Revises: c7a2e91d4b60
Create Date: 2026-08-03

Three new tables for the Security Center:

`security_events` — security signals about an identity. Deliberately
not folded into `audit_logs`: that table is workspace-scoped and
append-only for compliance ("who did what here"), while a security
event is usually user-scoped and frequently has no workspace or user at
all (a failed login for an unknown address still needs recording, and
dropping it would blind exactly the account-enumeration attempt it
evidences). Merging them would force a nullable workspace onto the
compliance log.

`trusted_devices` — keyed on a caller-supplied fingerprint rather than
a session id, because sessions rotate on every login and keying on one
would report every sign-in as a new device.

`password_policies` — 1:1 with `organizations`; no row means the
platform default applies, which is a real baseline rather than "no
rules".

`severity` and `event_type` are TEXT with a CHECK rather than Postgres
ENUMs. Postgres has no `ALTER TYPE ... DROP VALUE`, so an enum here
could never have a working `downgrade()` once a value was added — the
same reasoning that moved the role columns off `workspace_role` in
b3f7c1a9e582, and the pattern `api_keys.scope` already set.

Additive and reversible (Rule 19): three new tables, nothing existing
altered, so rolling back cannot break deployed code.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d5b3f8c2a916"
down_revision = "c7a2e91d4b60"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=False)

_SEVERITIES = ("info", "warning", "critical")
_EVENT_TYPES = (
    "login.new_device",
    "login.failed",
    "account.locked",
    "password.changed",
    "two_factor.enabled",
    "two_factor.disabled",
    "device.trusted",
    "device.revoked",
    "suspicious.ip",
    "suspicious.rapid_failures",
)


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.create_table(
        "security_events",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "workspace_id",
            _UUID,
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "organization_id",
            _UUID,
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"severity IN ({_quoted(_SEVERITIES)})",
            name="security_events_severity_check",
        ),
        sa.CheckConstraint(
            f"event_type IN ({_quoted(_EVENT_TYPES)})",
            name="security_events_event_type_check",
        ),
    )
    op.create_index("ix_security_events_user_id", "security_events", ["user_id"])
    op.create_index("ix_security_events_workspace_id", "security_events", ["workspace_id"])
    op.create_index("ix_security_events_organization_id", "security_events", ["organization_id"])
    op.create_index("ix_security_events_event_type", "security_events", ["event_type"])
    op.create_index("ix_security_events_severity", "security_events", ["severity"])
    # The feed is always read newest-first, and almost always for one
    # user — a composite beats the single-column index for that query.
    op.create_index(
        "ix_security_events_user_created",
        "security_events",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_security_events_created_at", "security_events", ["created_at"])

    op.create_table(
        "trusted_devices",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("device_fingerprint", sa.Text(), nullable=False),
        sa.Column("device_name", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column("trusted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "user_id", "device_fingerprint", name="uq_trusted_devices_user_fingerprint"
        ),
    )
    op.create_index("ix_trusted_devices_user_id", "trusted_devices", ["user_id"])

    op.create_table(
        "password_policies",
        sa.Column(
            "organization_id",
            _UUID,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("min_length", sa.Integer(), nullable=False),
        sa.Column("require_uppercase", sa.Boolean(), nullable=False),
        sa.Column("require_lowercase", sa.Boolean(), nullable=False),
        sa.Column("require_number", sa.Boolean(), nullable=False),
        sa.Column("require_symbol", sa.Boolean(), nullable=False),
        sa.Column("max_age_days", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_by_user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # A policy row must never be weaker than the platform baseline —
        # a "policy" that lowers the floor is not a feature worth having.
        sa.CheckConstraint("min_length >= 8", name="password_policies_min_length_check"),
    )


def downgrade() -> None:
    op.drop_table("password_policies")
    op.drop_index("ix_trusted_devices_user_id", table_name="trusted_devices")
    op.drop_table("trusted_devices")
    for index in (
        "ix_security_events_created_at",
        "ix_security_events_user_created",
        "ix_security_events_severity",
        "ix_security_events_event_type",
        "ix_security_events_organization_id",
        "ix_security_events_workspace_id",
        "ix_security_events_user_id",
    ):
        op.drop_index(index, table_name="security_events")
    op.drop_table("security_events")
