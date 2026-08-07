"""add GIN full-text search indexes

Revision ID: a1c7e35d9f84
Revises: e27b8f3d05a1
Create Date: 2026-08-07

Four indexes, no schema change.

**Expression indexes, not generated `tsvector` columns.** A stored
`GENERATED ... STORED` column is the textbook answer and the wrong one
here: adding it rewrites the whole table under an `ACCESS EXCLUSIVE`
lock, which on `agents` in a large workspace is a write outage for a
search feature. An expression index needs no column, no rewrite, and no
change to the schema `database-architect` owns — it is purely indexing
*within* that schema, which is where `postgresql-expert`'s remit sits.

**The expressions below are not written by hand.** They are what
`agentverse_api.infrastructure.full_text.searchable()` compiles to, and
every query goes through that same function. Postgres matches an
expression index by comparing parsed expression trees: if these two ever
drift by so much as a missing `coalesce`, the index is silently ignored
and every search sequentially scans. Nothing errors, nothing logs — it
just gets slow at exactly the data volume where it matters. The
integration suite asserts `EXPLAIN` picks a Bitmap Index Scan, which is
the only way that drift gets caught.

`CONCURRENTLY` (inside an autocommit block, since it cannot run in a
transaction) so building these does not lock out writes on a live table.

Primary access pattern served, per index: "find this workspace's live
<entity> by a prefix of any word in its name or description, ranked",
issued by `GET /api/v1/workspaces/{id}/search` and — for listings — by
the public catalog's `q` filter.
"""

from __future__ import annotations

from alembic import op

revision = "a1c7e35d9f84"
down_revision = "e27b8f3d05a1"
branch_labels = None
depends_on = None


#: `(table, index name, title column, subtitle column)`.
#: Listings search `title`/`summary`; the rest use `name`/`description`.
_TARGETS: tuple[tuple[str, str, str, str], ...] = (
    ("agents", "ix_agents_search", "name", "description"),
    ("knowledge_bases", "ix_knowledge_bases_search", "name", "description"),
    ("teams", "ix_teams_search", "name", "description"),
    ("marketplace_listings", "ix_marketplace_listings_search", "title", "summary"),
)


def _expression(title: str, subtitle: str) -> str:
    """Mirror of `full_text.searchable()`. See the module docstring."""
    return f"to_tsvector('english', (coalesce({title}, '') || ' ') || coalesce({subtitle}, ''))"


def upgrade() -> None:
    # `CREATE INDEX CONCURRENTLY` cannot run inside a transaction, and
    # Alembic wraps migrations in one by default.
    with op.get_context().autocommit_block():
        for table, index, title, subtitle in _TARGETS:
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index} "
                f"ON {table} USING GIN ({_expression(title, subtitle)})"
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for _table, index, _title, _subtitle in _TARGETS:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index}")
