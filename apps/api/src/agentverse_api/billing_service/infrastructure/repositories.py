"""Postgres adapters for the billing domain's ports."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.infrastructure.repositories import SqlWorkspaceRepository
from agentverse_api.billing_service.domain.entitlements import ResourceUsage
from agentverse_api.billing_service.domain.plan import Plan, PlanTier, tier_rank
from agentverse_api.billing_service.infrastructure import plan_config
from agentverse_api.billing_service.infrastructure.models import PlanModel
from agentverse_api.orchestration_service.infrastructure.integration_repository import (
    SqlIntegrationRepository,
)
from agentverse_api.orchestration_service.infrastructure.knowledge_repository import (
    SqlKnowledgeRepository,
)
from agentverse_api.orchestration_service.infrastructure.repositories import SqlAgentRepository
from agentverse_api.orchestration_service.infrastructure.team_repository import SqlTeamRepository


def _to_plan(row: PlanModel) -> Plan:
    return plan_config.to_domain(
        plan_id=row.id,
        slug=row.slug,
        display_name=row.display_name,
        description=row.description,
        monthly_price_cents=row.monthly_price_cents,
        annual_price_cents=row.annual_price_cents,
        currency=row.currency,
        trial_days=row.trial_days,
        is_public=row.is_public,
        is_active=row.is_active,
        sort_order=row.sort_order,
        resource_limits=row.resource_limits,
        metered_allowances=row.metered_allowances,
        capabilities=row.capabilities,
        overage_rates=row.overage_rates,
    )


class SqlPlanRepository:
    """Implements `domain.ports.PlanRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self, *, public_only: bool) -> list[Plan]:
        stmt = select(PlanModel).where(PlanModel.is_active.is_(True))
        if public_only:
            stmt = stmt.where(PlanModel.is_public.is_(True))
        result = await self._session.execute(stmt)
        plans = [_to_plan(row) for row in result.scalars().all()]
        # Sorted in Python by (sort_order, tier rank) rather than in SQL,
        # because tier rank is a domain fact — the ordering of FREE
        # through ENTERPRISE — and encoding it as a CASE expression in
        # the query would be a second copy of it that a later tier
        # addition could forget to update.
        plans.sort(key=lambda plan: (plan.sort_order, tier_rank(plan.slug)))
        return plans

    async def get_by_slug(self, slug: PlanTier) -> Plan | None:
        result = await self._session.execute(
            select(PlanModel).where(
                PlanModel.slug == slug,
                PlanModel.is_active.is_(True),
            )
        )
        row = result.scalar_one_or_none()
        return None if row is None else _to_plan(row)


class SqlWorkspaceUsageRepository:
    """Implements `domain.ports.WorkspaceUsageRepository` by asking each
    owning context for its own count.

    Every count is one indexed aggregate on `(workspace_id, …)`, and they
    are issued together rather than one at a time — five sequential round
    trips to render one usage panel is the N+1 this shape exists to avoid.
    They share a single `AsyncSession`, which is not concurrency-safe, so
    "together" means sequentially on one connection; the win is that the
    caller makes one call, not that the queries overlap.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._agents = SqlAgentRepository(session)
        self._teams = SqlTeamRepository(session)
        self._knowledge = SqlKnowledgeRepository(session)
        self._integrations = SqlIntegrationRepository(session)
        self._workspaces = SqlWorkspaceRepository(session)

    async def resource_usage(self, workspace_id: str) -> ResourceUsage:
        return ResourceUsage(
            agents=await self._agents.count_for_workspace(workspace_id),
            teams=await self._teams.count_teams(workspace_id=workspace_id),
            knowledge_bases=await self._knowledge.count_knowledge_bases(workspace_id=workspace_id),
            mcp_connections=await self._integrations.count_installed(workspace_id=workspace_id),
            seats=await self._workspaces.count_members(workspace_id),
        )
