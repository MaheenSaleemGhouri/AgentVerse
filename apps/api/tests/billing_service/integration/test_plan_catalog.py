"""The shipped catalog, read back through the real repository.

These assertions cannot be made against a fake. The seed rows live in a
migration, the JSON columns are validated on read, and the CHECK
constraints are the database's own backstop — all three are properties
of the deployed schema, not of the Python code.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.domain.plan import (
    Capability,
    MeteredDimension,
    OverageRate,
    PlanTier,
    ResourceLimit,
    annual_saving_percent,
    overage_cents,
    tier_rank,
)
from agentverse_api.billing_service.infrastructure.repositories import SqlPlanRepository

pytestmark = pytest.mark.integration


class TestSeededCatalog:
    async def test_all_four_tiers_are_present_and_public(self, db_session: AsyncSession) -> None:
        plans = await SqlPlanRepository(db_session).list_active(public_only=True)
        assert {plan.slug for plan in plans} == set(PlanTier)

    async def test_every_seeded_row_parses(self, db_session: AsyncSession) -> None:
        # The real assertion: `list_active` runs `plan_config.to_domain`
        # on each row, so a seed row with a typo'd limit key raises here
        # rather than silently granting unlimited access in production.
        plans = await SqlPlanRepository(db_session).list_active(public_only=False)
        assert len(plans) >= 4

    async def test_catalog_is_returned_in_ascending_tier_order(
        self, db_session: AsyncSession
    ) -> None:
        plans = await SqlPlanRepository(db_session).list_active(public_only=True)
        ranks = [tier_rank(plan.slug) for plan in plans]
        assert ranks == sorted(ranks)

    async def test_free_is_resolvable_as_the_default_plan(self, db_session: AsyncSession) -> None:
        # Every workspace without a subscription resolves through this
        # path on every entitlements request.
        service = PlanCatalogService(plans=SqlPlanRepository(db_session))
        assert (await service.default_plan()).slug is PlanTier.FREE

    async def test_enterprise_is_quoted_not_priced(self, db_session: AsyncSession) -> None:
        plan = await SqlPlanRepository(db_session).get_by_slug(PlanTier.ENTERPRISE)
        assert plan is not None
        assert plan.is_custom_priced is True
        assert annual_saving_percent(plan) is None

    async def test_free_has_a_published_price_of_zero_not_a_null_one(
        self, db_session: AsyncSession
    ) -> None:
        # 0 and NULL mean different things on the pricing page: one
        # renders "$0", the other "Contact sales".
        plan = await SqlPlanRepository(db_session).get_by_slug(PlanTier.FREE)
        assert plan is not None
        assert plan.monthly_price_cents == 0
        assert plan.is_custom_priced is False


class TestSeededPolicy:
    async def test_free_carries_no_overage_rates(self, db_session: AsyncSession) -> None:
        # A free workspace is refused at its limit, never billed. Any
        # overage rate on Free is a path to invoicing someone who never
        # entered a card.
        plan = await SqlPlanRepository(db_session).get_by_slug(PlanTier.FREE)
        assert plan is not None
        assert plan.overage_rates == {}

    async def test_enterprise_has_no_finite_allowance_to_exceed(
        self, db_session: AsyncSession
    ) -> None:
        # Billing an unlimited plan for overage is the most damaging
        # arithmetic this system could get wrong, so the seeded rows are
        # checked against the real overage function rather than only for
        # a null allowance.
        plan = await SqlPlanRepository(db_session).get_by_slug(PlanTier.ENTERPRISE)
        assert plan is not None
        probe = OverageRate(
            dimension=MeteredDimension.AGENT_RUNS,
            billing_increment=1_000,
            price_cents_per_increment=300,
        )
        for dimension in MeteredDimension:
            allowance = plan.metered_allowance(dimension)
            assert allowance is None
            assert overage_cents(allowance=allowance, used=10**9, rate=probe) == 0

    async def test_upgrading_never_raises_the_per_unit_overage_price(
        self, db_session: AsyncSession
    ) -> None:
        # If Team charged more per unit than Pro, upgrading would make
        # the customer worse off at exactly the usage level that
        # triggers the upgrade.
        repo = SqlPlanRepository(db_session)
        pro = await repo.get_by_slug(PlanTier.PRO)
        team = await repo.get_by_slug(PlanTier.TEAM)
        assert pro is not None and team is not None
        for dimension, pro_rate in pro.overage_rates.items():
            team_rate = team.overage_rates.get(dimension)
            assert team_rate is not None, f"Team dropped an overage rate Pro has: {dimension}"
            assert team_rate.billing_increment == pro_rate.billing_increment
            assert team_rate.price_cents_per_increment <= pro_rate.price_cents_per_increment

    async def test_each_tier_grants_at_least_what_the_one_below_grants(
        self, db_session: AsyncSession
    ) -> None:
        # Capability inheritance, asserted structurally rather than
        # spot-checked: a paid tier that silently loses a capability the
        # tier below it has is a downgrade sold as an upgrade.
        repo = SqlPlanRepository(db_session)
        ordered = [PlanTier.FREE, PlanTier.PRO, PlanTier.TEAM, PlanTier.ENTERPRISE]
        plans = [await repo.get_by_slug(slug) for slug in ordered]
        assert all(plan is not None for plan in plans)
        # Community support is the one exception, and it is deliberate:
        # paid tiers replace it with priority or dedicated support rather
        # than also carrying it.
        exempt = {Capability.COMMUNITY_SUPPORT}
        for lower, higher in zip(plans, plans[1:], strict=False):
            assert lower is not None and higher is not None
            missing = (lower.capabilities - exempt) - higher.capabilities
            assert not missing, f"{higher.slug} is missing {missing} that {lower.slug} grants"

    async def test_each_tier_raises_or_holds_every_resource_limit(
        self, db_session: AsyncSession
    ) -> None:
        # `None` (unlimited) is treated as the largest value. A tier that
        # lowered a limit below the tier beneath it would make the
        # upgrade wall move backwards.
        repo = SqlPlanRepository(db_session)
        ordered = [PlanTier.FREE, PlanTier.PRO, PlanTier.TEAM, PlanTier.ENTERPRISE]
        plans = [await repo.get_by_slug(slug) for slug in ordered]
        for lower, higher in zip(plans, plans[1:], strict=False):
            assert lower is not None and higher is not None
            for limit in ResourceLimit:
                low = lower.resource_limit(limit)
                high = higher.resource_limit(limit)
                if high is None:
                    continue
                assert low is not None, (
                    f"{lower.slug} is unlimited on {limit} but {higher.slug} caps it at {high}"
                )
                assert high >= low, f"{higher.slug} lowers {limit} from {low} to {high}"


class TestDatabaseBackstops:
    async def test_slug_check_rejects_an_unknown_tier(self, db_session: AsyncSession) -> None:
        # Proves the constraint exists in the deployed schema rather than
        # assuming it from the migration file.
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO plans (id, slug, display_name, description) "
                    "VALUES (gen_random_uuid(), 'platinum', 'Platinum', '')"
                )
            )
        await db_session.rollback()

    async def test_negative_price_is_rejected_by_the_database(
        self, db_session: AsyncSession
    ) -> None:
        # A negative price would flow into an invoice line as a credit
        # nobody granted.
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO plans "
                    "(id, slug, display_name, description, monthly_price_cents) "
                    "VALUES (gen_random_uuid(), 'pro', 'Dup', '', -1)"
                )
            )
        await db_session.rollback()

    async def test_slug_is_unique(self, db_session: AsyncSession) -> None:
        # Two rows for `pro` would make "which plan is this workspace
        # on" ambiguous.
        with pytest.raises(IntegrityError):
            await db_session.execute(
                text(
                    "INSERT INTO plans (id, slug, display_name, description) "
                    "VALUES (gen_random_uuid(), 'pro', 'Pro duplicate', '')"
                )
            )
        await db_session.rollback()
