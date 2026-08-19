"""phase 12: api_keys.kind (user_api_key vs mcp_client)

Revision ID: 8c1d444558ec
Revises: 9011ed21fa17
Create Date: 2026-08-19

Reuses the existing `api_keys` table for AgentVerse's own MCP server
credentials (docs/adr/0017) rather than a parallel table — same hash/
scope/revoke/rotate logic, genuinely reused. `kind` is the only new
column: it says which surface a credential authenticates against, so a
leaked MCP integration token can never be replayed against the ordinary
`/api/v1/*` REST API and vice versa (enforced at the auth boundary, not
just documented here).

Backfilled to `'user_api_key'` for every existing row via the column
default — every key issued before this migration was, by construction,
a personal/service API key.
"""

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "8c1d444558ec"
down_revision: Union[str, None] = "9011ed21fa17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("kind", sa.Text(), nullable=False, server_default="user_api_key"),
    )
    op.create_check_constraint(
        "ck_api_keys_kind", "api_keys", "kind IN ('user_api_key', 'mcp_client')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_api_keys_kind", "api_keys", type_="check")
    op.drop_column("api_keys", "kind")
