"""Plan arithmetic. Every test here names the money or access bug it
prevents, because that is the useful part of a billing test suite.
"""

from __future__ import annotations

import pytest

from agentverse_api.billing_service.domain.plan import (
    BillingInterval,
    Capability,
    MeteredDimension,
    OverageRate,
    Plan,
    PlanTier,
    ResourceLimit,
    annual_saving_percent,
    is_downgrade,
    is_upgrade,
    overage_cents,
    overage_units,
    price_cents,
    remaining,
    tier_rank,
    usage_percent,
    within_resource_limit,
)


def _plan(
    *,
    slug: PlanTier = PlanTier.PRO,
    monthly: int | None = 2_900,
    annual: int | None = 29_000,
    resource_limits: dict[ResourceLimit, int | None] | None = None,
    metered_allowances: dict[MeteredDimension, int | None] | None = None,
    capabilities: frozenset[Capability] = frozenset(),
    overage_rates: dict[MeteredDimension, OverageRate] | None = None,
) -> Plan:
    return Plan(
        id="plan-1",
        slug=slug,
        display_name=slug.value.title(),
        description="",
        monthly_price_cents=monthly,
        annual_price_cents=annual,
        currency="usd",
        trial_days=14,
        is_public=True,
        is_active=True,
        sort_order=1,
        resource_limits=resource_limits or {},
        metered_allowances=metered_allowances or {},
        capabilities=capabilities,
        overage_rates=overage_rates or {},
    )


class TestTierOrdering:
    def test_every_tier_has_a_rank(self) -> None:
        # Asserted over the enum rather than spot-checked: a fifth tier
        # added without a rank would otherwise raise KeyError the first
        # time someone changed plan in production, not in CI.
        for tier in PlanTier:
            assert isinstance(tier_rank(tier), int)

    def test_ranks_are_strictly_increasing_free_to_enterprise(self) -> None:
        ordered = [PlanTier.FREE, PlanTier.PRO, PlanTier.TEAM, PlanTier.ENTERPRISE]
        ranks = [tier_rank(tier) for tier in ordered]
        assert ranks == sorted(ranks)
        assert len(set(ranks)) == len(ranks)

    def test_upgrade_and_downgrade_are_mutually_exclusive(self) -> None:
        # Both true at once would mean a plan change gets prorated
        # immediately *and* scheduled for period end — charging twice for
        # one transition.
        for current in PlanTier:
            for target in PlanTier:
                up = is_upgrade(current=current, target=target)
                down = is_downgrade(current=current, target=target)
                assert not (up and down)
                if current == target:
                    assert not up and not down


class TestResourceLimits:
    def test_none_means_unlimited(self) -> None:
        assert within_resource_limit(limit=None, current=10_000) is True
        assert remaining(limit=None, used=5) is None
        assert usage_percent(limit=None, used=5) is None

    def test_refuses_at_the_limit_not_one_past_it(self) -> None:
        # 100 of 100 must refuse the 101st. Off by one here is a
        # customer getting an agent they did not pay for.
        assert within_resource_limit(limit=100, current=99) is True
        assert within_resource_limit(limit=100, current=100) is False
        assert within_resource_limit(limit=100, current=101) is False

    def test_zero_limit_refuses_everything(self) -> None:
        # How a tier says "this resource is not part of your plan" as a
        # number: Free has teams=0.
        assert within_resource_limit(limit=0, current=0) is False

    def test_remaining_never_goes_negative(self) -> None:
        # A workspace over its limit (grandfathered, or downgraded)
        # must show 0 remaining, not "-3 remaining".
        assert remaining(limit=5, used=8) == 0

    def test_usage_percent_caps_at_100(self) -> None:
        assert usage_percent(limit=10, used=25) == 100

    def test_usage_percent_is_none_on_a_zero_limit(self) -> None:
        # 0/0 has no percentage. Reporting 100% would fire an "upgrade
        # to get more" nudge for a dimension the upgrade does not add.
        assert usage_percent(limit=0, used=0) is None

    def test_plan_returns_none_for_an_unconfigured_dimension(self) -> None:
        plan = _plan(resource_limits={ResourceLimit.AGENTS: 5})
        assert plan.resource_limit(ResourceLimit.AGENTS) == 5
        assert plan.resource_limit(ResourceLimit.TEAMS) is None


class TestOverage:
    RATE = OverageRate(
        dimension=MeteredDimension.AGENT_RUNS,
        billing_increment=1_000,
        price_cents_per_increment=300,
    )

    def test_no_overage_within_allowance(self) -> None:
        assert overage_units(allowance=10_000, used=10_000, increment=1_000) == 0
        assert overage_cents(allowance=10_000, used=9_999, rate=self.RATE) == 0

    def test_partial_increment_rounds_up(self) -> None:
        # One run over a 10,000 allowance bills a full 1,000-run
        # increment. Rounding down would let a workspace sit permanently
        # 999 runs into overage and never pay for any of it.
        assert overage_units(allowance=10_000, used=10_001, increment=1_000) == 1
        assert overage_cents(allowance=10_000, used=10_001, rate=self.RATE) == 300

    def test_exact_increment_does_not_round_to_the_next_one(self) -> None:
        assert overage_units(allowance=10_000, used=11_000, increment=1_000) == 1
        assert overage_units(allowance=10_000, used=11_001, increment=1_000) == 2

    def test_unlimited_allowance_is_never_in_overage(self) -> None:
        # Enterprise. Billing an unlimited plan for overage is the single
        # most damaging arithmetic bug this module could ship.
        assert overage_units(allowance=None, used=10**9, increment=1_000) == 0
        assert overage_cents(allowance=None, used=10**9, rate=self.RATE) == 0

    def test_zero_increment_is_rejected_rather_than_dividing_by_zero(self) -> None:
        with pytest.raises(ValueError, match="increment must be positive"):
            overage_units(allowance=0, used=1, increment=0)

    def test_rate_rejects_a_non_positive_increment_at_construction(self) -> None:
        with pytest.raises(ValueError, match="billing_increment must be positive"):
            OverageRate(
                dimension=MeteredDimension.TOKENS,
                billing_increment=0,
                price_cents_per_increment=100,
            )

    def test_rate_rejects_a_negative_price(self) -> None:
        # A negative rate would turn overage into a credit — money paid
        # out for exceeding a quota.
        with pytest.raises(ValueError, match="must not be negative"):
            OverageRate(
                dimension=MeteredDimension.TOKENS,
                billing_increment=1_000,
                price_cents_per_increment=-1,
            )

    def test_overage_is_always_an_integer_number_of_cents(self) -> None:
        # Rule 15. A float anywhere in this path compounds into
        # cent-level invoice discrepancies.
        result = overage_cents(allowance=1_000, used=123_456, rate=self.RATE)
        assert isinstance(result, int)
        assert not isinstance(result, bool)


class TestPricing:
    def test_price_selects_by_interval(self) -> None:
        plan = _plan(monthly=2_900, annual=29_000)
        assert price_cents(plan, BillingInterval.MONTHLY) == 2_900
        assert price_cents(plan, BillingInterval.ANNUAL) == 29_000

    def test_custom_priced_plan_returns_none_rather_than_zero(self) -> None:
        # Zero would render as "Free" on the pricing page for the tier
        # that costs the most.
        plan = _plan(slug=PlanTier.ENTERPRISE, monthly=None, annual=None)
        assert plan.is_custom_priced is True
        assert price_cents(plan, BillingInterval.MONTHLY) is None
        assert annual_saving_percent(plan) is None

    def test_free_plan_is_not_custom_priced(self) -> None:
        # 0 is a published price; NULL is an absent one. Collapsing them
        # would put "Contact sales" on the Free tier.
        plan = _plan(slug=PlanTier.FREE, monthly=0, annual=0)
        assert plan.is_custom_priced is False
        assert annual_saving_percent(plan) is None

    def test_annual_saving_is_truncated_not_rounded_up(self) -> None:
        # 29,000 against 34,800 is 16.66%. Claiming 17% overstates a
        # commercial promise; understating is the safe direction.
        plan = _plan(monthly=2_900, annual=29_000)
        assert annual_saving_percent(plan) == 16

    def test_no_saving_when_annual_costs_at_least_twelve_months(self) -> None:
        plan = _plan(monthly=1_000, annual=12_000)
        assert annual_saving_percent(plan) is None


class TestCapabilities:
    def test_grants_only_what_is_listed(self) -> None:
        plan = _plan(capabilities=frozenset({Capability.SSO, Capability.ANALYTICS}))
        assert plan.grants(Capability.SSO) is True
        assert plan.grants(Capability.WHITE_LABEL) is False
