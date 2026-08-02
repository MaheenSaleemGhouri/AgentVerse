"""add api key rotation and scope

Revision ID: cc70c017a8d3
Revises: 8d925c92da0a
Create Date: 2026-07-30

API keys could previously only be issued and revoked, never rotated,
and carried no scope/tier.

`scope`/`tier` are plain TEXT with a server default, not a Postgres
ENUM: `ApiKeyScope` is validated at the Pydantic boundary, and a TEXT
column never needs a migration to add an allowed value later — an
ENUM's values are not cleanly reversible to drop (Rule 19).

`rotated_from_id` is a nullable self-referential FK forming an
audit-followable chain from a rotated key back to the one it replaced;
every pre-existing key has it `NULL` (issued directly).

Additive and reversible: new columns only, existing rows get the
server defaults, nothing existing altered (Rule 19).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "cc70c017a8d3"
down_revision = "8d925c92da0a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("scope", sa.Text(), nullable=False, server_default="full"),
    )
    op.add_column(
        "api_keys",
        sa.Column("tier", sa.Text(), nullable=False, server_default="standard"),
    )
    op.add_column(
        "api_keys",
        sa.Column(
            "rotated_from_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("api_keys.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "rotated_from_id")
    op.drop_column("api_keys", "tier")
    op.drop_column("api_keys", "scope")
