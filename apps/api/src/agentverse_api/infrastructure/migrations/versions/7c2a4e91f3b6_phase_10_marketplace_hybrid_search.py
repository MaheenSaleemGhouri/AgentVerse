"""phase 10: hybrid (semantic + keyword) marketplace search

Revision ID: 7c2a4e91f3b6
Revises: 0958619d3576
Create Date: 2026-08-18

Three nullable columns on `marketplace_listings` (never a second table —
one listing has one current searchable text, unlike `kb_chunks` which
has many chunks per document) plus a partial HNSW index scoped to
`status = 'published' AND embedding IS NOT NULL`: the vector arm only
ever ranks published, already-embedded listings, so an index over the
whole table (mostly drafts with no embedding yet) would be mostly dead
weight.

Nullable rather than backfilled-then-required: an existing listing has
no embedding until it next transitions through `approve`/`relist`
(`marketplace_service.py`), and search degrades gracefully to the
existing keyword-only path for anything not yet embedded — never a hard
failure (`hybrid_marketplace_search.py`).
"""

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = "7c2a4e91f3b6"
down_revision: Union[str, None] = "0958619d3576"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Matches the dimension every other embedding column in this schema uses
# (`kb_chunks.embedding`, Phase 5) — the same `OpenAIEmbeddingProvider`
# default. Hardcoded per that migration's own precedent: a migration is a
# historical record and must not silently reshape if application code
# later switches embedding model.
_EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.add_column(
        "marketplace_listings", sa.Column("embedding", Vector(_EMBEDDING_DIM), nullable=True)
    )
    op.add_column(
        "marketplace_listings", sa.Column("embedding_model", sa.Text(), nullable=True)
    )
    op.add_column(
        "marketplace_listings", sa.Column("embedding_model_version", sa.Text(), nullable=True)
    )

    # CONCURRENTLY cannot run inside a transaction, and Alembic wraps
    # migrations in one by default (`a1c7e35d9f84` precedent).
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_marketplace_listings_embedding_hnsw "
            "ON marketplace_listings USING hnsw (embedding vector_cosine_ops) "
            "WHERE status = 'published' AND embedding IS NOT NULL"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_marketplace_listings_embedding_hnsw")
    op.drop_column("marketplace_listings", "embedding_model_version")
    op.drop_column("marketplace_listings", "embedding_model")
    op.drop_column("marketplace_listings", "embedding")
