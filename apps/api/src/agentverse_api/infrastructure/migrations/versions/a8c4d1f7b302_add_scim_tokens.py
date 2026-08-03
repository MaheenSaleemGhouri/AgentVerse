"""add scim_tokens

Revision ID: a8c4d1f7b302
Revises: f4b8d1e6c037
Create Date: 2026-08-02

SCIM 2.0 provisioning is org-scoped, for the same reason SSO is
(ADR-0011): the identity provider that authenticates an organization's
people is the one that should also create and deprovision them.

The bearer token an IdP presents is hashed at rest with the same fast
hash `api_keys` uses — it is already high-entropy, so Argon2id would be
pure overhead (CLAUDE.md §10's own distinction) — and shown in full
exactly once, at issuance.

Deliberately a separate credential from `api_keys`: an API key is
workspace-scoped and acts with a member's role, while a SCIM token is
organization-scoped and acts only on membership. Overloading one table
would have meant a nullable `organization_id` on `api_keys` and a scope
value that means "not actually a workspace key at all".

Additive and reversible (Rule 19): one new table, nothing existing
altered.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a8c4d1f7b302"
down_revision = "f4b8d1e6c037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scim_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        #: Displayed so an admin can tell two tokens apart in the UI
        #: without the secret ever being retrievable again.
        sa.Column("token_prefix", sa.Text(), nullable=False),
        sa.Column("hashed_token", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "created_by_user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        #: Revocation keeps the row rather than deleting it, mirroring
        #: `api_keys.revoked_at` — a deprovisioning credential's history
        #: is exactly what an auditor asks for.
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_scim_tokens_organization_id"),
        "scim_tokens",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_scim_tokens_organization_id"), table_name="scim_tokens")
    op.drop_table("scim_tokens")
