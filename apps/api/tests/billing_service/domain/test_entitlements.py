"""Turning a plan plus real counts into "may I, and how close am I?"."""

from __future__ import annotations

from agentverse_api.billing_service.domain.entitlements import (
    NUDGE_THRESHOLD_PERCENT,
    ResourceUsage,
    can_create,
    metered_lines,
    resource_lines,
)
from agentverse_api.billing_service.domain.plan import (
    Capability,
    MeteredDimension,
    Plan,
    PlanTier,
    ResourceLimit,
)


def _plan(
    *,
    resource_limits: dict[ResourceLimit, int | None] | None = None,
    metered_allowances: dict[MeteredDimension, int | None] | None = None,
) -> Plan:
    return Plan(
        id="plan-1",
        slug=PlanTier.PRO,
        display_name="Pro",
        description="",
        monthly_price_cents=2_900,
        annual_price_cents=29_000,
        currency="usd",
        trial_days=14,
        is_public=True,
        is_active=True,
        sort_order=1,
        resource_limits=resource_limits or {},
        metered_allowances=metered_allowances or {},
        capabilities=frozenset({Capability.ANALYTICS}),
        overage_rates={},
    )


def _usage(**overrides: int) -> ResourceUsage:
    base = {"agents": 0, "teams": 0, "knowledge_bases": 0, "mcp_connections": 0, "seats": 1}
    base.update(overrides)
    return ResourceUsage(**base)  # type: ignore[arg-type]


class TestResourceLines:
    def test_omits_dimensions_the_snapshot_cannot_measure(self) -> None:
        # Concurrent runs is a live queue property, not a row count.
        # Reporting it as 0 used would show headroom that was never
        # measured.
        lines = resource_lines(plan=_plan(), usage=_usage())
        dimensions = {line.dimension for line in lines}
        assert ResourceLimit.CONCURRENT_RUNS.value not in dimensions
        assert ResourceLimit.AGENTS.value in dimensions

    def test_order_follows_the_enum_not_dict_iteration(self) -> None:
        # A stable row order matters: the usage panel must not reshuffle
        # between two refreshes that changed nothing.
        expected = [
            limit.value for limit in ResourceLimit if limit is not ResourceLimit.CONCURRENT_RUNS
        ]
        lines = resource_lines(plan=_plan(), usage=_usage())
        assert [line.dimension for line in lines] == expected

    def test_at_limit_is_true_when_used_equals_limit(self) -> None:
        plan = _plan(resource_limits={ResourceLimit.AGENTS: 3})
        line = next(
            line
            for line in resource_lines(plan=plan, usage=_usage(agents=3))
            if line.dimension == ResourceLimit.AGENTS.value
        )
        assert line.at_limit is True
        assert line.remaining == 0
        assert line.percent_used == 100

    def test_unlimited_dimension_reports_null_limit_and_null_remaining(self) -> None:
        plan = _plan(resource_limits={ResourceLimit.AGENTS: None})
        line = next(
            line
            for line in resource_lines(plan=plan, usage=_usage(agents=9_999))
            if line.dimension == ResourceLimit.AGENTS.value
        )
        assert line.limit is None
        assert line.remaining is None
        assert line.percent_used is None
        assert line.at_limit is False
        # An unlimited dimension can never be "approaching" a limit, so
        # it must not trigger an upgrade nudge.
        assert line.approaching_limit is False

    def test_approaching_limit_fires_at_the_shared_threshold(self) -> None:
        # The threshold lives in one constant so the usage panel and the
        # notification job cannot disagree about when to warn.
        plan = _plan(resource_limits={ResourceLimit.AGENTS: 10})
        below = next(
            line
            for line in resource_lines(plan=plan, usage=_usage(agents=7))
            if line.dimension == ResourceLimit.AGENTS.value
        )
        at = next(
            line
            for line in resource_lines(plan=plan, usage=_usage(agents=8))
            if line.dimension == ResourceLimit.AGENTS.value
        )
        assert NUDGE_THRESHOLD_PERCENT == 80
        assert below.approaching_limit is False
        assert at.approaching_limit is True


class TestMeteredLines:
    def test_every_metered_dimension_is_reported_even_with_no_usage(self) -> None:
        # Absent from the usage map genuinely is zero here: metered usage
        # accrues from an append-only stream, so "no rows" is a fact, not
        # a failed measurement.
        lines = metered_lines(plan=_plan(), period_usage={})
        assert [line.dimension for line in lines] == [d.value for d in MeteredDimension]
        assert all(line.used == 0 for line in lines)

    def test_reports_usage_against_the_plan_allowance(self) -> None:
        plan = _plan(metered_allowances={MeteredDimension.AGENT_RUNS: 10_000})
        line = next(
            line
            for line in metered_lines(plan=plan, period_usage={MeteredDimension.AGENT_RUNS: 9_000})
            if line.dimension == MeteredDimension.AGENT_RUNS.value
        )
        assert line.limit == 10_000
        assert line.used == 9_000
        assert line.remaining == 1_000
        assert line.percent_used == 90
        assert line.approaching_limit is True
        assert line.at_limit is False


class TestCanCreate:
    def test_refuses_at_the_limit(self) -> None:
        plan = _plan(resource_limits={ResourceLimit.AGENTS: 3})
        assert can_create(plan=plan, limit=ResourceLimit.AGENTS, current_count=2) is True
        assert can_create(plan=plan, limit=ResourceLimit.AGENTS, current_count=3) is False

    def test_unconfigured_dimension_is_unlimited_not_forbidden(self) -> None:
        # Adding a new dimension to the enum must not retroactively
        # forbid it on every existing plan row.
        assert can_create(plan=_plan(), limit=ResourceLimit.TEAMS, current_count=500) is True
