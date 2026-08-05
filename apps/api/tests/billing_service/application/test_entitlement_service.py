"""Entitlement resolution, against in-memory repositories."""

from __future__ import annotations

from agentverse_api.billing_service.application.entitlement_service import EntitlementService
from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.domain.entitlements import ResourceUsage
from agentverse_api.billing_service.domain.plan import (
    Capability,
    MeteredDimension,
    Plan,
    PlanTier,
    ResourceLimit,
)
from tests.billing_service.fakes import (
    FakePlanRepository,
    FakeSubscriptionRepository,
    FakeUsageRepository,
)


def _free_plan() -> Plan:
    return Plan(
        id="plan-free",
        slug=PlanTier.FREE,
        display_name="Free",
        description="",
        monthly_price_cents=0,
        annual_price_cents=0,
        currency="usd",
        trial_days=0,
        is_public=True,
        is_active=True,
        sort_order=0,
        resource_limits={
            ResourceLimit.AGENTS: 3,
            ResourceLimit.TEAMS: 0,
            ResourceLimit.KNOWLEDGE_BASES: 1,
            ResourceLimit.MCP_CONNECTIONS: 1,
            ResourceLimit.SEATS: 1,
            ResourceLimit.CONCURRENT_RUNS: 1,
        },
        metered_allowances={MeteredDimension.AGENT_RUNS: 500},
        capabilities=frozenset({Capability.COMMUNITY_SUPPORT}),
        overage_rates={},
    )


def _service(
    usage: ResourceUsage, *, plans: list[Plan] | None = None
) -> tuple[EntitlementService, FakeUsageRepository, FakeSubscriptionRepository]:
    repo = FakeUsageRepository(usage)
    subscriptions = FakeSubscriptionRepository()
    service = EntitlementService(
        catalog=PlanCatalogService(plans=FakePlanRepository(plans or [_free_plan()])),
        usage=repo,
        subscriptions=subscriptions,
    )
    return service, repo, subscriptions


class TestEntitlementsFor:
    async def test_workspace_with_no_subscription_resolves_to_free(self) -> None:
        service, _, _ = _service(
            ResourceUsage(agents=1, teams=0, knowledge_bases=0, mcp_connections=0, seats=1)
        )
        result = await service.entitlements_for("ws-1")
        assert result.plan.slug is PlanTier.FREE
        assert result.workspace_id == "ws-1"

    async def test_reports_real_counts_not_zeros(self) -> None:
        service, _, _ = _service(
            ResourceUsage(agents=2, teams=0, knowledge_bases=1, mcp_connections=1, seats=4)
        )
        result = await service.entitlements_for("ws-1")
        by_dimension = {line.dimension: line for line in result.resources}
        assert by_dimension[ResourceLimit.AGENTS.value].used == 2
        assert by_dimension[ResourceLimit.SEATS.value].used == 4

    async def test_a_workspace_over_its_seat_limit_reports_at_limit(self) -> None:
        # Real state, not hypothetical: a workspace that added members
        # before a downgrade sits above its new limit and must be shown
        # as such rather than as having negative headroom.
        service, _, _ = _service(
            ResourceUsage(agents=0, teams=0, knowledge_bases=0, mcp_connections=0, seats=4)
        )
        result = await service.entitlements_for("ws-1")
        seats = next(
            line for line in result.resources if line.dimension == ResourceLimit.SEATS.value
        )
        assert seats.at_limit is True
        assert seats.remaining == 0

    async def test_metered_lines_report_zero_until_metering_records_events(self) -> None:
        # Honest rather than fabricated: the dimensions and allowances are
        # real, and zero is the true count of events recorded so far.
        service, _, _ = _service(
            ResourceUsage(agents=0, teams=0, knowledge_bases=0, mcp_connections=0, seats=1)
        )
        result = await service.entitlements_for("ws-1")
        runs = next(
            line for line in result.metered if line.dimension == MeteredDimension.AGENT_RUNS.value
        )
        assert runs.used == 0
        assert runs.limit == 500

    async def test_capabilities_come_from_the_plan(self) -> None:
        service, _, _ = _service(
            ResourceUsage(agents=0, teams=0, knowledge_bases=0, mcp_connections=0, seats=1)
        )
        result = await service.entitlements_for("ws-1")
        assert result.grants(Capability.COMMUNITY_SUPPORT) is True
        assert result.grants(Capability.SSO) is False


class TestMayCreate:
    async def test_refuses_once_the_limit_is_reached(self) -> None:
        service, _, _ = _service(
            ResourceUsage(agents=3, teams=0, knowledge_bases=0, mcp_connections=0, seats=1)
        )
        assert await service.may_create(workspace_id="ws-1", limit=ResourceLimit.AGENTS) is False

    async def test_admits_below_the_limit(self) -> None:
        service, _, _ = _service(
            ResourceUsage(agents=2, teams=0, knowledge_bases=0, mcp_connections=0, seats=1)
        )
        assert await service.may_create(workspace_id="ws-1", limit=ResourceLimit.AGENTS) is True

    async def test_zero_limit_refuses_the_first_one(self) -> None:
        # Free has teams=0 — "not part of your plan", expressed as a
        # number.
        service, _, _ = _service(
            ResourceUsage(agents=0, teams=0, knowledge_bases=0, mcp_connections=0, seats=1)
        )
        assert await service.may_create(workspace_id="ws-1", limit=ResourceLimit.TEAMS) is False

    async def test_re_measures_rather_than_trusting_a_caller_supplied_count(self) -> None:
        # A caller-supplied count would be a client-controlled quota
        # check wearing a server-side disguise (Rule 6). Proven by the
        # repository actually being hit.
        service, repo, _ = _service(
            ResourceUsage(agents=3, teams=0, knowledge_bases=0, mcp_connections=0, seats=1)
        )
        await service.may_create(workspace_id="ws-1", limit=ResourceLimit.AGENTS)
        assert repo.calls == 1

    async def test_unmeasured_dimension_admits_rather_than_blocking(self) -> None:
        # Concurrent runs is enforced at submission against the queue.
        # Refusing here — on a number nobody evaluated — would block a
        # legitimate action for a limit that was never checked.
        service, _, _ = _service(
            ResourceUsage(agents=0, teams=0, knowledge_bases=0, mcp_connections=0, seats=1)
        )
        assert (
            await service.may_create(workspace_id="ws-1", limit=ResourceLimit.CONCURRENT_RUNS)
            is True
        )


class TestGrants:
    async def test_reads_the_capability_off_the_resolved_plan(self) -> None:
        service, _, _ = _service(
            ResourceUsage(agents=0, teams=0, knowledge_bases=0, mcp_connections=0, seats=1)
        )
        assert await service.grants(workspace_id="ws-1", capability=Capability.SSO) is False
        assert (
            await service.grants(workspace_id="ws-1", capability=Capability.COMMUNITY_SUPPORT)
            is True
        )
