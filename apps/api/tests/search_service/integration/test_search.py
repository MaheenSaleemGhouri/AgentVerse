"""Search against real Postgres.

Four things only the database can prove, each of which reaches a
customer rather than a log if it breaks:

- the GIN indexes are **actually used** — an expression index that no
  longer matches its query is ignored silently, with no error and no log
  line, and only shows up as a slow endpoint at production data volume;
- a search never crosses a workspace boundary (Rule 11), including when
  two workspaces name an agent identically;
- soft-deleted rows stay deleted, so search is not a back door to them;
- prefix matching, ranking and the published-only catalog filter behave
  the way the palette assumes.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.infrastructure.full_text import SearchColumn, search_query
from agentverse_api.marketplace_service.infrastructure.models import MarketplaceListingModel
from agentverse_api.marketplace_service.infrastructure.repositories import SqlListingRepository
from agentverse_api.orchestration_service.infrastructure.knowledge_repository import (
    SqlKnowledgeRepository,
)
from agentverse_api.orchestration_service.infrastructure.models import (
    AgentModel,
    KnowledgeBaseModel,
    TeamModel,
)
from agentverse_api.orchestration_service.infrastructure.repositories import SqlAgentRepository
from agentverse_api.orchestration_service.infrastructure.team_repository import SqlTeamRepository
from agentverse_api.search_service.application.search_service import SearchService
from agentverse_api.search_service.domain.kinds import SearchKind
from agentverse_api.search_service.domain.results import SearchGroup, SearchResults
from agentverse_api.search_service.infrastructure.searchers import (
    AgentSearcher,
    KnowledgeBaseSearcher,
    ListingSearcher,
    TeamSearcher,
)

pytestmark = pytest.mark.integration


async def _workspace(session: AsyncSession) -> str:
    workspace_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO workspaces (id, name, slug, created_at) VALUES (:id, :name, :slug, now())"
        ),
        {"id": workspace_id, "name": "Search Test", "slug": f"ws-{workspace_id[:8]}"},
    )
    await session.flush()
    return workspace_id


async def _user(session: AsyncSession) -> str:
    user_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO users (id, email, name, email_verified, created_at, updated_at) "
            "VALUES (:id, :email, 'Search Tester', true, now(), now())"
        ),
        {"id": user_id, "email": f"search-{user_id[:8]}@example.test"},
    )
    await session.flush()
    return user_id


async def _agent(
    session: AsyncSession,
    *,
    workspace_id: str,
    user_id: str,
    name: str,
    description: str | None = None,
    deleted: bool = False,
) -> str:
    agent_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO agents "
            "(id, workspace_id, name, description, status, created_by_user_id, "
            " created_at, updated_at, deleted_at) "
            "VALUES (:id, :ws, :name, :description, 'draft', :user, now(), now(), "
            " CASE WHEN :deleted THEN now() ELSE NULL END)"
        ),
        {
            "id": agent_id,
            "ws": workspace_id,
            "name": name,
            "description": description,
            "user": user_id,
            "deleted": deleted,
        },
    )
    await session.flush()
    return agent_id


def _service(session: AsyncSession) -> SearchService:
    return SearchService(
        searchers=[
            AgentSearcher(SqlAgentRepository(session)),
            KnowledgeBaseSearcher(SqlKnowledgeRepository(session)),
            TeamSearcher(SqlTeamRepository(session)),
            ListingSearcher(SqlListingRepository(session)),
        ]
    )


def _group(results: SearchResults, kind: SearchKind) -> SearchGroup:
    return next(group for group in results.groups if group.kind is kind)


class TestIndexIsActuallyUsed:
    """The gate that catches expression drift.

    `enable_seqscan = off` rather than inserting a million rows: on a
    small table Postgres prefers a sequential scan whatever the indexes
    say, so the plan would prove nothing. With it disabled, a query whose
    expression still matches the index picks the index — and one whose
    expression has drifted from the migration *still* falls back to a
    Seq Scan, which is exactly the regression being guarded against.
    """

    @pytest.mark.parametrize(
        ("index_name", "id_column", "title_column", "subtitle_column"),
        [
            ("ix_agents_search", AgentModel.id, AgentModel.name, AgentModel.description),
            (
                "ix_knowledge_bases_search",
                KnowledgeBaseModel.id,
                KnowledgeBaseModel.name,
                KnowledgeBaseModel.description,
            ),
            ("ix_teams_search", TeamModel.id, TeamModel.name, TeamModel.description),
            (
                "ix_marketplace_listings_search",
                MarketplaceListingModel.slug,
                MarketplaceListingModel.title,
                MarketplaceListingModel.summary,
            ),
        ],
    )
    async def test_the_planner_picks_the_gin_index(
        self,
        db_session: AsyncSession,
        index_name: str,
        id_column: SearchColumn[str],
        title_column: SearchColumn[str],
        subtitle_column: SearchColumn[str | None],
    ) -> None:
        await db_session.execute(text("SET enable_seqscan = off"))
        statement = search_query(
            id_column=id_column,
            title_column=title_column,
            subtitle_column=subtitle_column,
            tsquery="sal:*",
            where=[],
            limit=5,
        )
        compiled = statement.compile(
            dialect=db_session.bind.dialect,  # type: ignore[union-attr]
            compile_kwargs={"literal_binds": True},
        )
        result = await db_session.execute(text(f"EXPLAIN {compiled}"))
        plan = "\n".join(row[0] for row in result)
        assert index_name in plan, (
            f"{index_name} was not used. The expression in "
            f"`full_text.searchable()` has drifted from the one the "
            f"migration indexed:\n{plan}"
        )


class TestTenantIsolation:
    async def test_a_search_never_crosses_a_workspace(self, db_session: AsyncSession) -> None:
        user_id = await _user(db_session)
        mine = await _workspace(db_session)
        theirs = await _workspace(db_session)
        await _agent(db_session, workspace_id=mine, user_id=user_id, name="Sales qualifier")
        await _agent(db_session, workspace_id=theirs, user_id=user_id, name="Sales qualifier")

        results = await _service(db_session).search(workspace_id=mine, query="sales")
        hits = _group(results, SearchKind.AGENT).matches

        # Both workspaces have an identically-named agent, so a missing
        # tenant predicate returns two rows here and one is a leak.
        assert len(hits) == 1

    async def test_another_workspaces_row_is_absent_not_merely_unranked(
        self, db_session: AsyncSession
    ) -> None:
        user_id = await _user(db_session)
        mine = await _workspace(db_session)
        theirs = await _workspace(db_session)
        leaked = await _agent(
            db_session, workspace_id=theirs, user_id=user_id, name="Confidential migration bot"
        )
        await _agent(db_session, workspace_id=mine, user_id=user_id, name="Migration helper")

        results = await _service(db_session).search(workspace_id=mine, query="migration")
        assert leaked not in {hit.id for hit in _group(results, SearchKind.AGENT).matches}


class TestMatching:
    async def test_a_partial_word_finds_the_whole_one(self, db_session: AsyncSession) -> None:
        user_id = await _user(db_session)
        workspace_id = await _workspace(db_session)
        await _agent(db_session, workspace_id=workspace_id, user_id=user_id, name="Sales qualifier")

        results = await _service(db_session).search(workspace_id=workspace_id, query="sal qual")
        titles = [hit.title for hit in _group(results, SearchKind.AGENT).matches]
        assert "Sales qualifier" in titles

    async def test_the_description_is_searched_too(self, db_session: AsyncSession) -> None:
        user_id = await _user(db_session)
        workspace_id = await _workspace(db_session)
        await _agent(
            db_session,
            workspace_id=workspace_id,
            user_id=user_id,
            name="Helper",
            description="Reviews pull requests for security regressions.",
        )

        results = await _service(db_session).search(workspace_id=workspace_id, query="security")
        assert len(_group(results, SearchKind.AGENT).matches) == 1

    async def test_an_agent_with_no_description_is_still_findable(
        self, db_session: AsyncSession
    ) -> None:
        # Without `coalesce` in the indexed expression, a NULL
        # description makes the whole concatenation NULL and the agent
        # becomes invisible under its own name.
        user_id = await _user(db_session)
        workspace_id = await _workspace(db_session)
        await _agent(
            db_session,
            workspace_id=workspace_id,
            user_id=user_id,
            name="Orphan agent",
            description=None,
        )

        results = await _service(db_session).search(workspace_id=workspace_id, query="orphan")
        assert len(_group(results, SearchKind.AGENT).matches) == 1

    async def test_a_soft_deleted_agent_is_not_findable(self, db_session: AsyncSession) -> None:
        user_id = await _user(db_session)
        workspace_id = await _workspace(db_session)
        await _agent(
            db_session,
            workspace_id=workspace_id,
            user_id=user_id,
            name="Deleted saboteur",
            deleted=True,
        )

        results = await _service(db_session).search(workspace_id=workspace_id, query="saboteur")
        assert _group(results, SearchKind.AGENT).matches == ()

    async def test_a_name_match_outranks_a_description_only_match(
        self, db_session: AsyncSession
    ) -> None:
        user_id = await _user(db_session)
        workspace_id = await _workspace(db_session)
        await _agent(
            db_session,
            workspace_id=workspace_id,
            user_id=user_id,
            name="Unrelated helper",
            description="Occasionally mentions invoices somewhere in a long description.",
        )
        await _agent(db_session, workspace_id=workspace_id, user_id=user_id, name="Invoice reader")

        results = await _service(db_session).search(workspace_id=workspace_id, query="invoice")
        hits = _group(results, SearchKind.AGENT).matches
        assert hits[0].title == "Invoice reader"


class TestLimits:
    async def test_has_more_reflects_the_database_not_the_fixture(
        self, db_session: AsyncSession
    ) -> None:
        user_id = await _user(db_session)
        workspace_id = await _workspace(db_session)
        for index in range(4):
            await _agent(
                db_session,
                workspace_id=workspace_id,
                user_id=user_id,
                name=f"Reporting agent {index}",
            )

        results = await _service(db_session).search(
            workspace_id=workspace_id, query="reporting", limit_per_kind=2
        )
        group = _group(results, SearchKind.AGENT)
        assert len(group.matches) == 2
        assert group.has_more is True


class TestCatalog:
    async def test_only_published_listings_are_searchable(self, db_session: AsyncSession) -> None:
        # The catalog searcher is the one with no workspace predicate, so
        # `status` is doing all of the security work: without it, every
        # workspace's drafts would be readable from every other
        # workspace's search box.
        publisher = await _workspace(db_session)
        draft_slug = f"draft-{uuid.uuid4().hex[:8]}"
        await db_session.execute(
            text(
                "INSERT INTO marketplace_listings "
                "(id, publisher_workspace_id, slug, title, summary, description, kind, "
                " status, pricing, price_cents, category_slug, is_featured, is_official, "
                " install_count, rating_sum, rating_count, created_at, updated_at) "
                "VALUES (:id, :ws, :slug, 'Undisclosed pipeline tool', "
                " 'A summary nobody outside should read.', 'x', 'agent', 'draft', 'free', 0, "
                " 'productivity', false, false, 0, 0, 0, now(), now())"
            ),
            {"id": str(uuid.uuid4()), "ws": publisher, "slug": draft_slug},
        )
        await db_session.flush()

        results = await _service(db_session).search(
            workspace_id=publisher, query="undisclosed", kinds=[SearchKind.LISTING]
        )
        assert _group(results, SearchKind.LISTING).matches == ()
