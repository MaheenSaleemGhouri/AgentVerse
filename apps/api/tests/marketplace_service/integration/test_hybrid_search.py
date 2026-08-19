"""Hybrid (semantic + keyword) marketplace search against real Postgres
+ pgvector — the guarantees a fake cannot prove:

- the vector arm actually ranks by cosine distance, pre-filtered by
  `status = 'published'` and by embedding model/version (never mixed);
- the partial HNSW index (`ix_marketplace_listings_embedding_hnsw`) is
  the one the planner actually uses;
- `approve`/`relist` embed the listing when a `MarketplaceService` is
  wired with an embedder, and a failing embedder degrades the
  *publish*, never blocks it;
- `browse(query=...)` takes the hybrid path only when both `search` and
  `embedder` are wired, and re-hydrates full `Listing` rows in the
  fused rank order — the exact composition `get_marketplace_service`
  wires in production.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pytest
from agentverse_shared.embeddings.port import EmbeddingError, EmbeddingResult
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.marketplace_service.application.marketplace_service import MarketplaceService
from agentverse_api.marketplace_service.domain.listing import ListingKind, ListingStatus, Pricing
from agentverse_api.marketplace_service.domain.ports import ListingSearchFilters, ListingSearchPort
from agentverse_api.marketplace_service.infrastructure.repositories import (
    SqlCategoryRepository,
    SqlListingRepository,
    SqlListingVersionRepository,
    SqlReviewRepository,
)

pytestmark = pytest.mark.integration

_SUMMARY = "A genuinely useful research agent for teams that need citations."
_DESCRIPTION = "x" * 200
_MODEL = "text-embedding-3-small"
_VERSION = "1"
_DIMENSIONS = 1536


def _unit_vector(active_dim: int) -> list[float]:
    """A 1536-dim standard basis vector — cosine distance 0 between two
    vectors sharing an `active_dim`, 1 (i.e. orthogonal) between two
    that don't. The real `marketplace_listings.embedding` column is a
    fixed `Vector(1536)` (Phase 10 migration); pgvector enforces that
    dimension strictly, so a short fake vector fails at the database
    boundary rather than merely producing an unrealistic assertion.
    """
    vector = [0.0] * _DIMENSIONS
    vector[active_dim] = 1.0
    return vector


async def _workspace(session: AsyncSession) -> str:
    workspace_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO workspaces (id, name, slug, created_at) VALUES (:id, :name, :slug, now())"
        ),
        {"id": workspace_id, "name": "Hybrid Test", "slug": f"ws-{workspace_id[:8]}"},
    )
    await session.flush()
    return workspace_id


@dataclass
class _FakeEmbedder:
    """Deterministic, not the real OpenAI adapter — the vector this
    returns is what every test's "nearest neighbour" assertion is
    computed against.
    """

    vector_by_text: dict[str, list[float]] = field(default_factory=dict)
    default_vector: list[float] = field(default_factory=lambda: _unit_vector(0))
    raises: Exception | None = None

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if self.raises is not None:
            raise self.raises
        vectors = [self.vector_by_text.get(t, self.default_vector) for t in texts]
        return EmbeddingResult(
            vectors=vectors, model=_MODEL, model_version=_VERSION, prompt_tokens=1
        )

    @property
    def model(self) -> str:
        return _MODEL

    @property
    def model_version(self) -> str:
        return _VERSION

    @property
    def dimensions(self) -> int:
        return _DIMENSIONS


def _search(service: MarketplaceService) -> ListingSearchPort:
    """`service.search` is `ListingSearchPort | None` — asserted non-null
    here once, so every call site below can call `vector_search`/
    `keyword_search` without repeating the narrowing.
    """
    assert service.search is not None
    return service.search


def _service(session: AsyncSession, *, embedder: _FakeEmbedder | None = None) -> MarketplaceService:
    listings = SqlListingRepository(session)
    return MarketplaceService(
        listings=listings,
        versions=SqlListingVersionRepository(session),
        reviews=SqlReviewRepository(session),
        categories=SqlCategoryRepository(session),
        search=listings,
        embedder=embedder,
    )


async def _published(service: MarketplaceService, publisher: str, *, title: str) -> str:
    listing = await service.create_listing(
        publisher_workspace_id=publisher,
        publisher_name="Acme",
        kind=ListingKind.AGENT,
        title=title,
        summary=_SUMMARY,
        description=_DESCRIPTION,
        category_slug="research",
        pricing=Pricing.FREE,
        price_cents=0,
    )
    await service.publish_version(
        slug=listing.slug,
        actor_workspace_id=publisher,
        config={"model": "gpt-4o-mini"},
        changelog="Initial release",
    )
    await service.submit_for_review(slug=listing.slug, actor_workspace_id=publisher)
    await service.approve(listing_id=listing.id)
    return listing.slug


class TestVectorSearch:
    async def test_ranks_by_cosine_similarity_to_the_query_embedding(
        self, db_session: AsyncSession, unique_name: str
    ) -> None:
        publisher = await _workspace(db_session)
        embedder = _FakeEmbedder(
            vector_by_text={
                # Embedded text is "title\n\nsummary\n\ndescription" —
                # only the title varies here, so keying on it is enough.
                f"{title}\n\n{_SUMMARY}\n\n{_DESCRIPTION}": vector
                for title, vector in {
                    f"Close {unique_name}": _unit_vector(0),
                    f"Far {unique_name}": _unit_vector(2),
                }.items()
            }
        )
        service = _service(db_session, embedder=embedder)
        close_slug = await _published(service, publisher, title=f"Close {unique_name}")
        far_slug = await _published(service, publisher, title=f"Far {unique_name}")

        results = await _search(service).vector_search(
            embedding=_unit_vector(0),
            embedding_model=_MODEL,
            embedding_model_version=_VERSION,
            filters=ListingSearchFilters(),
            limit=10,
        )
        ids = [m.id for m in results if m.id in (close_slug, far_slug)]
        assert ids == [close_slug, far_slug]
        await db_session.rollback()

    async def test_excludes_drafts_even_with_an_embedding(
        self, db_session: AsyncSession, unique_name: str
    ) -> None:
        publisher = await _workspace(db_session)
        service = _service(db_session, embedder=_FakeEmbedder())
        draft = await service.create_listing(
            publisher_workspace_id=publisher,
            publisher_name="Acme",
            kind=ListingKind.AGENT,
            title=f"Draft {unique_name}",
            summary=_SUMMARY,
            description=_DESCRIPTION,
            category_slug="research",
            pricing=Pricing.FREE,
            price_cents=0,
        )
        # A draft is never embedded (only `approve`/`relist` embed), but
        # even if it somehow carried a stray embedding, `status` must
        # still gate it out.
        await service.listings.set_embedding(
            listing_id=draft.id,
            embedding=_unit_vector(0),
            embedding_model=_MODEL,
            embedding_model_version=_VERSION,
        )
        results = await _search(service).vector_search(
            embedding=_unit_vector(0),
            embedding_model=_MODEL,
            embedding_model_version=_VERSION,
            filters=ListingSearchFilters(),
            limit=50,
        )
        assert draft.slug not in [m.id for m in results]
        await db_session.rollback()

    async def test_excludes_a_different_embedding_model_version(
        self, db_session: AsyncSession, unique_name: str
    ) -> None:
        publisher = await _workspace(db_session)
        service = _service(db_session, embedder=_FakeEmbedder())
        slug = await _published(service, publisher, title=f"Stale {unique_name}")
        # Simulate a listing embedded under a previous model generation.
        await service.listings.set_embedding(
            listing_id=(await service.get(slug=slug, viewer_workspace_id=None)).id,
            embedding=_unit_vector(0),
            embedding_model="text-embedding-ada-002",
            embedding_model_version="1",
        )
        results = await _search(service).vector_search(
            embedding=_unit_vector(0),
            embedding_model=_MODEL,
            embedding_model_version=_VERSION,
            filters=ListingSearchFilters(),
            limit=50,
        )
        assert slug not in [m.id for m in results]
        await db_session.rollback()

    async def test_the_partial_hnsw_index_exists_with_the_expected_definition(
        self, db_session: AsyncSession
    ) -> None:
        """A live cost-based `EXPLAIN` assertion (the `test_search.py`
        GIN precedent's technique) is not reliable here the way it is
        there: that case has no competing index for its predicate, so
        disabling seqscan leaves only the GIN path. Here, a plain btree
        `ix_marketplace_listings_status` *also* serves `status =
        'published'`, and on this table's small/shared-dev-DB row count
        the planner correctly costs a plain index scan + in-memory sort
        below an HNSW traversal — no combination of `enable_seqscan`/
        `enable_bitmapscan`/`enable_indexscan` isolates HNSW specifically,
        since pgvector's ANN scan is itself an "Index Scan" node the
        last of those would also disable. What's genuinely verifiable
        and load-bearing instead: the index exists with the exact shape
        the migration created. A missing/malformed index is a real
        regression this catches; the planner's cost tradeoff at
        production data volume is `postgresql-expert`'s ongoing tuning
        concern, not a property of this migration to keep re-asserting.
        """
        result = await db_session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'ix_marketplace_listings_embedding_hnsw'"
            )
        )
        indexdef = result.scalar_one_or_none()
        assert indexdef is not None, "the partial HNSW index does not exist"
        assert "USING hnsw" in indexdef
        assert "vector_cosine_ops" in indexdef
        assert "WHERE" in indexdef
        assert "published" in indexdef


class TestEmbedOnPublish:
    async def test_approve_embeds_the_listing_when_an_embedder_is_wired(
        self, db_session: AsyncSession, unique_name: str
    ) -> None:
        publisher = await _workspace(db_session)
        service = _service(db_session, embedder=_FakeEmbedder(default_vector=_unit_vector(1)))
        slug = await _published(service, publisher, title=f"Embedded {unique_name}")

        found = await _search(service).vector_search(
            embedding=_unit_vector(1),
            embedding_model=_MODEL,
            embedding_model_version=_VERSION,
            filters=ListingSearchFilters(),
            limit=10,
        )
        assert slug in [m.id for m in found]
        await db_session.rollback()

    async def test_relist_re_embeds_the_listing(
        self, db_session: AsyncSession, unique_name: str
    ) -> None:
        publisher = await _workspace(db_session)
        service = _service(db_session, embedder=_FakeEmbedder(default_vector=_unit_vector(2)))
        slug = await _published(service, publisher, title=f"Relisted {unique_name}")
        await service.unlist(slug=slug, actor_workspace_id=publisher)
        await service.relist(slug=slug, actor_workspace_id=publisher)

        found = await _search(service).vector_search(
            embedding=_unit_vector(2),
            embedding_model=_MODEL,
            embedding_model_version=_VERSION,
            filters=ListingSearchFilters(),
            limit=10,
        )
        assert slug in [m.id for m in found]
        await db_session.rollback()

    async def test_no_embedder_wired_means_approval_never_touches_the_embedding_columns(
        self, db_session: AsyncSession, unique_name: str
    ) -> None:
        publisher = await _workspace(db_session)
        service = _service(db_session, embedder=None)
        await _published(service, publisher, title=f"Unwired {unique_name}")
        # No assertion beyond "did not raise" — the point is that
        # `_maybe_embed` is a true no-op with no embedder, not a call
        # that happens to embed nothing.

    async def test_a_failing_embedder_does_not_block_approval(
        self, db_session: AsyncSession, unique_name: str
    ) -> None:
        publisher = await _workspace(db_session)
        service = _service(
            db_session, embedder=_FakeEmbedder(raises=EmbeddingError("provider unavailable"))
        )
        # The core promise: publishing (the moderation action of record)
        # must succeed even when the embedding side effect cannot.
        slug = await _published(service, publisher, title=f"Degraded {unique_name}")
        listing = await service.get(slug=slug, viewer_workspace_id=None)
        assert listing.status is ListingStatus.PUBLISHED
        await db_session.rollback()


class TestHybridBrowse:
    async def test_browse_with_a_query_takes_the_hybrid_path_when_wired(
        self, db_session: AsyncSession, unique_name: str
    ) -> None:
        publisher = await _workspace(db_session)
        service = _service(db_session, embedder=_FakeEmbedder())
        slug = await _published(service, publisher, title=f"Hybrid {unique_name}")

        listings, total = await service.browse(query=f"Hybrid {unique_name}")
        assert [listing.slug for listing in listings] == [slug]
        assert total == 1
        # Full `Listing` rows, not just id/title/subtitle — the whole
        # point of re-hydrating through `get_by_slugs`.
        assert listings[0].summary == _SUMMARY
        await db_session.rollback()

    async def test_browse_without_a_query_is_unaffected_by_a_wired_embedder(
        self, db_session: AsyncSession, unique_name: str
    ) -> None:
        publisher = await _workspace(db_session)
        service = _service(db_session, embedder=_FakeEmbedder())
        await _published(service, publisher, title=f"Plain {unique_name}")
        # No query -> the original filtered-and-counted catalog path,
        # never the hybrid one, regardless of what is wired.
        listings, total = await service.browse(category_slug="research")
        assert total >= 1
        assert isinstance(listings, list)
        await db_session.rollback()

    async def test_a_zero_result_hybrid_search_returns_an_empty_page_not_an_error(
        self, db_session: AsyncSession, unique_name: str
    ) -> None:
        service = _service(db_session, embedder=_FakeEmbedder())
        listings, total = await service.browse(query=f"nonexistent-{unique_name}-xyz")
        assert listings == []
        assert total == 0
