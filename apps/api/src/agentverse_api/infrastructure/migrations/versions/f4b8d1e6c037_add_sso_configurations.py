"""add sso_configurations

Revision ID: f4b8d1e6c037
Revises: e3a7c2d5b926
Create Date: 2026-08-01

Increment 8a: org-scoped SSO configuration (ADR-0011 — SSO is one of the
three things an organization actually groups workspaces *for*).

`protocol` is plain TEXT, app-validated, **not** a Postgres ENUM: 8b adds
`"saml"` to the allowed values, and ENUM values are not cleanly
reversible to drop (Rule 19) — the same reasoning already applied to
`api_keys.scope` and `resource_permissions.resource_type`.

`protocol_config` is JSONB so protocol-specific fields (SAML's
IdP metadata URL and signing certificate; OIDC's extra scopes) do not
each need their own column and a migration per protocol.

The client secret is stored with the **existing**
`agentverse_shared.security.envelope.CredentialVault` AES-256-GCM
envelope already used for MCP integration credentials — three columns
(`client_secret_ciphertext`, `wrapped_dek`, `key_version`), not new
crypto (CLAUDE.md §10: never hand-rolled).

One enabled config per organization per protocol is enforced by a
partial unique index rather than application logic, so two concurrent
writers cannot both succeed.

Additive and reversible (Rule 19): one new table, nothing existing
altered.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f4b8d1e6c037"
down_revision = "e3a7c2d5b926"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sso_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("protocol", sa.Text(), nullable=False),
        #: The vendor preset this was created from (`azure_ad`, `okta`,
        #: `google_workspace`, `generic`). UI convenience only — there is
        #: deliberately no per-vendor server code branching on it (8c).
        sa.Column("preset", sa.Text(), nullable=False, server_default="generic"),
        sa.Column("issuer_url", sa.Text(), nullable=True),
        sa.Column("client_id", sa.Text(), nullable=True),
        sa.Column("client_secret_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("wrapped_dek", sa.LargeBinary(), nullable=True),
        sa.Column("key_version", sa.Text(), nullable=True),
        sa.Column(
            "protocol_config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_by_user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_sso_configurations_organization_id"),
        "sso_configurations",
        ["organization_id"],
        unique=False,
    )
    # At most one *enabled* config per (organization, protocol) — a
    # partial index, so any number of disabled drafts can coexist.
    op.create_index(
        "uq_sso_enabled_per_org_protocol",
        "sso_configurations",
        ["organization_id", "protocol"],
        unique=True,
        postgresql_where=sa.text("enabled"),
    )


def downgrade() -> None:
    op.drop_index("uq_sso_enabled_per_org_protocol", table_name="sso_configurations")
    op.drop_index(op.f("ix_sso_configurations_organization_id"), table_name="sso_configurations")
    op.drop_table("sso_configurations")
