"""Invoice assembly.

Every amount asserted here is worked out by hand in a comment rather than
recomputed with the implementation's own expression — a test that
re-derives the code proves only that Python is deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime

from agentverse_api.billing_service.domain.invoice import build_draft_invoice
from agentverse_api.billing_service.domain.plan import (
    BillingInterval,
    Capability,
    MeteredDimension,
    OverageRate,
    Plan,
)
from agentverse_api.billing_service.domain.usage import DimensionUsage, PeriodUsage

_START = datetime(2026, 8, 1, tzinfo=UTC)
_END = datetime(2026, 9, 1, tzinfo=UTC)


def _plan(
    *,
    monthly: int | None = 2900,
    allowances: dict[MeteredDimension, int | None] | None = None,
    rates: dict[MeteredDimension, OverageRate] | None = None,
    display_name: str = "Pro",
) -> Plan:
    from agentverse_api.billing_service.domain.plan import PlanTier

    return Plan(
        id="plan-pro",
        slug=PlanTier.PRO,
        display_name=display_name,
        description="",
        monthly_price_cents=monthly,
        annual_price_cents=None if monthly is None else monthly * 10,
        currency="usd",
        trial_days=14,
        is_public=True,
        is_active=True,
        sort_order=1,
        resource_limits={},
        # `is None`, not `or`: an empty dict is falsy, and a plan with
        # deliberately *no* overage rates is exactly what the Free-tier
        # assertion below needs to construct.
        metered_allowances=(
            {MeteredDimension.AGENT_RUNS: 10_000} if allowances is None else allowances
        ),
        capabilities=frozenset({Capability.COMMUNITY_SUPPORT}),
        overage_rates=(
            {
                MeteredDimension.AGENT_RUNS: OverageRate(
                    dimension=MeteredDimension.AGENT_RUNS,
                    billing_increment=1_000,
                    price_cents_per_increment=300,
                )
            }
            if rates is None
            else rates
        ),
    )


def _usage(**quantities: int) -> PeriodUsage:
    return PeriodUsage(
        workspace_id="ws-1",
        period_start=_START,
        period_end=_END,
        dimensions={
            MeteredDimension(name): DimensionUsage(
                dimension=MeteredDimension(name), quantity=quantity, cost_micro_usd=0
            )
            for name, quantity in quantities.items()
        },
    )


class TestFlatFee:
    def test_a_period_with_no_usage_is_just_the_plan_fee(self) -> None:
        invoice = build_draft_invoice(
            plan=_plan(), interval=BillingInterval.MONTHLY, usage=_usage()
        )
        assert [line.kind for line in invoice.lines] == ["subscription"]
        assert invoice.subtotal_cents == 2900
        assert invoice.has_overage is False

    def test_the_annual_interval_bills_the_annual_price(self) -> None:
        invoice = build_draft_invoice(plan=_plan(), interval=BillingInterval.ANNUAL, usage=_usage())
        assert invoice.subtotal_cents == 29000

    def test_a_custom_priced_plan_contributes_no_flat_line(self) -> None:
        # Enterprise is quoted and invoiced by sales; inventing a zero
        # would render as "$0.00" on a page next to real usage.
        invoice = build_draft_invoice(
            plan=_plan(monthly=None), interval=BillingInterval.MONTHLY, usage=_usage()
        )
        assert invoice.lines == []


class TestOverage:
    def test_usage_within_the_allowance_produces_no_overage_line(self) -> None:
        invoice = build_draft_invoice(
            plan=_plan(), interval=BillingInterval.MONTHLY, usage=_usage(agent_runs=9_999)
        )
        assert invoice.has_overage is False

    def test_usage_exactly_at_the_allowance_produces_no_overage_line(self) -> None:
        invoice = build_draft_invoice(
            plan=_plan(), interval=BillingInterval.MONTHLY, usage=_usage(agent_runs=10_000)
        )
        assert invoice.has_overage is False

    def test_one_unit_over_bills_a_whole_increment(self) -> None:
        # Rounding up is the industry convention and the only choice that
        # keeps the sum of parts from under-billing the whole.
        invoice = build_draft_invoice(
            plan=_plan(), interval=BillingInterval.MONTHLY, usage=_usage(agent_runs=10_001)
        )
        overage = next(line for line in invoice.lines if line.kind == "overage")
        # 1 run over, billed as one 1,000-run increment at 300c.
        assert overage.amount_cents == 300
        assert overage.quantity == 1
        assert invoice.subtotal_cents == 3200

    def test_a_partial_final_increment_rounds_up(self) -> None:
        invoice = build_draft_invoice(
            plan=_plan(), interval=BillingInterval.MONTHLY, usage=_usage(agent_runs=14_500)
        )
        overage = next(line for line in invoice.lines if line.kind == "overage")
        # 4,500 over -> 5 increments (ceil 4.5) at 300c = 1500c.
        assert overage.amount_cents == 1500
        assert invoice.subtotal_cents == 4400

    def test_a_dimension_with_no_overage_rate_is_never_billed(self) -> None:
        # This is what makes Free genuinely free: it carries no overage
        # rates, so a free workspace is refused at its limit and there is
        # no code path that can invoice it.
        free = _plan(
            monthly=0,
            allowances={MeteredDimension.AGENT_RUNS: 500},
            rates={},
            display_name="Free",
        )
        invoice = build_draft_invoice(
            plan=free, interval=BillingInterval.MONTHLY, usage=_usage(agent_runs=50_000)
        )
        assert invoice.has_overage is False
        assert invoice.subtotal_cents == 0

    def test_an_unlimited_allowance_is_never_in_overage(self) -> None:
        unlimited = _plan(allowances={MeteredDimension.AGENT_RUNS: None})
        invoice = build_draft_invoice(
            plan=unlimited,
            interval=BillingInterval.MONTHLY,
            usage=_usage(agent_runs=10**9),
        )
        assert invoice.has_overage is False

    def test_the_overage_line_names_the_dimension_and_the_allowance(self) -> None:
        # A customer disputing a charge needs to see what drove it.
        invoice = build_draft_invoice(
            plan=_plan(), interval=BillingInterval.MONTHLY, usage=_usage(agent_runs=12_000)
        )
        overage = next(line for line in invoice.lines if line.kind == "overage")
        assert overage.dimension is MeteredDimension.AGENT_RUNS
        assert "10,000" in overage.description
        assert "2,000" in overage.description


class TestLineOrdering:
    def test_the_flat_fee_comes_first(self) -> None:
        invoice = build_draft_invoice(
            plan=_plan(), interval=BillingInterval.MONTHLY, usage=_usage(agent_runs=12_000)
        )
        assert invoice.lines[0].kind == "subscription"

    def test_overages_are_listed_in_a_stable_order(self) -> None:
        # Declaration order, not dictionary-insertion order, so two
        # invoices for the same workspace can be compared by eye.
        rates = {
            dimension: OverageRate(
                dimension=dimension, billing_increment=1_000, price_cents_per_increment=100
            )
            for dimension in (MeteredDimension.TOKENS, MeteredDimension.AGENT_RUNS)
        }
        plan = _plan(
            allowances={MeteredDimension.AGENT_RUNS: 0, MeteredDimension.TOKENS: 0},
            rates=rates,
        )
        first = build_draft_invoice(
            plan=plan,
            interval=BillingInterval.MONTHLY,
            usage=_usage(tokens=5_000, agent_runs=5_000),
        )
        second = build_draft_invoice(
            plan=plan,
            interval=BillingInterval.MONTHLY,
            usage=_usage(agent_runs=5_000, tokens=5_000),
        )
        assert [line.dimension for line in first.lines] == [line.dimension for line in second.lines]
        # AGENT_RUNS is declared before TOKENS in the enum.
        assert first.lines[1].dimension is MeteredDimension.AGENT_RUNS


class TestPlatformCost:
    def test_micro_usd_is_converted_to_cents_exactly_once(self) -> None:
        usage = PeriodUsage(
            workspace_id="ws-1",
            period_start=_START,
            period_end=_END,
            dimensions={
                MeteredDimension.TOKENS: DimensionUsage(
                    dimension=MeteredDimension.TOKENS,
                    quantity=1_000_000,
                    # 1 cent = 10,000 micro-USD, so 355,000 -> 35.5c,
                    # rounded half-up to 36c.
                    cost_micro_usd=355_000,
                )
            },
        )
        invoice = build_draft_invoice(plan=_plan(), interval=BillingInterval.MONTHLY, usage=usage)
        assert invoice.platform_cost_cents == 36

    def test_platform_cost_is_not_part_of_the_subtotal(self) -> None:
        # Charging it would bill the customer our supplier costs rather
        # than our published prices.
        usage = PeriodUsage(
            workspace_id="ws-1",
            period_start=_START,
            period_end=_END,
            dimensions={
                MeteredDimension.TOKENS: DimensionUsage(
                    dimension=MeteredDimension.TOKENS,
                    quantity=1_000_000,
                    cost_micro_usd=9_000_000,
                )
            },
        )
        invoice = build_draft_invoice(plan=_plan(), interval=BillingInterval.MONTHLY, usage=usage)
        assert invoice.platform_cost_cents == 900
        assert invoice.subtotal_cents == 2900
