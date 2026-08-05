"""Usage aggregation, quota enforcement, and invoice assembly end to end.

The clock is injected everywhere, so period rollovers and finalization
windows are driven by moving a variable rather than by waiting.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agentverse_api.billing_service.application.entitlement_service import EntitlementService
from agentverse_api.billing_service.application.invoicing_service import (
    InvoicingService,
    PeriodNotFinalizedError,
)
from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.application.quota_service import (
    QuotaExceededError,
    QuotaService,
)
from agentverse_api.billing_service.application.subscription_service import SubscriptionService
from agentverse_api.billing_service.application.usage_service import (
    UsageService,
    calendar_month_bounds,
)
from agentverse_api.billing_service.domain.entitlements import ResourceUsage
from agentverse_api.billing_service.domain.plan import (
    BillingInterval,
    Capability,
    MeteredDimension,
    OverageRate,
    Plan,
    PlanTier,
)
from agentverse_api.billing_service.domain.usage import UsageEvent, UsageSource
from tests.billing_service.fakes import (
    FakeCustomerRepository,
    FakeMeteredUsageRepository,
    FakePlanRepository,
    FakeSubscriptionRepository,
)

_T0 = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


def _rate(dimension: MeteredDimension, *, increment: int = 1_000, cents: int = 300) -> OverageRate:
    return OverageRate(
        dimension=dimension,
        billing_increment=increment,
        price_cents_per_increment=cents,
    )


def _plans() -> list[Plan]:
    def build(
        slug: PlanTier,
        *,
        monthly: int | None,
        runs: int | None,
        billable: bool,
    ) -> Plan:
        return Plan(
            id=f"plan-{slug.value}",
            slug=slug,
            display_name=slug.value.title(),
            description="",
            monthly_price_cents=monthly,
            annual_price_cents=None if monthly is None else monthly * 10,
            currency="usd",
            trial_days=0,
            is_public=True,
            is_active=True,
            sort_order=0,
            resource_limits={},
            metered_allowances={MeteredDimension.AGENT_RUNS: runs},
            capabilities=frozenset({Capability.COMMUNITY_SUPPORT}),
            overage_rates=(
                {MeteredDimension.AGENT_RUNS: _rate(MeteredDimension.AGENT_RUNS)}
                if billable
                else {}
            ),
        )

    return [
        # Free: a hard limit, no overage rate — refused, never billed.
        build(PlanTier.FREE, monthly=0, runs=500, billable=False),
        # Pro: billable overage beyond the allowance.
        build(PlanTier.PRO, monthly=2900, runs=10_000, billable=True),
        # Team stands in for the unlimited case. Not Enterprise: that
        # tier is custom-priced and deliberately cannot be self-served,
        # so a fixture that subscribed to it would be testing a path the
        # product refuses.
        build(PlanTier.TEAM, monthly=9900, runs=None, billable=False),
    ]


class _Fixture:
    def __init__(self) -> None:
        self.clock = _Clock(_T0)
        self._next_run = 0
        self.plans = _plans()
        self.subscription_repo = FakeSubscriptionRepository()
        for plan in self.plans:
            self.subscription_repo.seed_plan(plan.id, plan.slug)
        catalog = PlanCatalogService(plans=FakePlanRepository(self.plans))
        self.subscriptions = SubscriptionService(
            subscriptions=self.subscription_repo,
            customers=FakeCustomerRepository(),
            catalog=catalog,
            now=self.clock,
        )
        self.usage_repo = FakeMeteredUsageRepository()
        self.usage = UsageService(
            usage=self.usage_repo, subscriptions=self.subscriptions, now=self.clock
        )
        self.entitlements = EntitlementService(
            catalog=catalog,
            usage=_ZeroResourceUsage(),
            subscriptions=self.subscription_repo,
            metered=self.usage,
        )
        self.quota = QuotaService(entitlements=self.entitlements, usage=self.usage)
        self.invoicing = InvoicingService(usage=self.usage, catalog=catalog)

    async def subscribe(self, slug: PlanTier) -> None:
        await self.subscriptions.start(
            workspace_id="ws-1",
            plan_slug=slug,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key=f"start-{slug.value}",
            with_trial=False,
        )

    async def use_runs(self, count: int, *, at: datetime | None = None) -> None:
        """Record `count` distinct runs.

        The run counter is a fixture-level sequence rather than
        `range(count)` per call: restarting the ids would reproduce the
        same idempotency keys, and the second batch would be silently
        deduplicated against the first — which is correct behaviour
        making for a misleading test.
        """
        moment = at or self.clock.now
        events = []
        for _ in range(count):
            self._next_run += 1
            run_id = f"run-{self._next_run}"
            events.append(
                UsageEvent(
                    workspace_id="ws-1",
                    dimension=MeteredDimension.AGENT_RUNS,
                    quantity=1,
                    occurred_at=moment,
                    source=UsageSource.AGENT_RUN,
                    source_id=run_id,
                    idempotency_key=f"run:{run_id}:agent_runs",
                )
            )
        await self.usage.record(events)


class _ZeroResourceUsage:
    async def resource_usage(self, workspace_id: str) -> ResourceUsage:
        del workspace_id
        return ResourceUsage(agents=0, teams=0, knowledge_bases=0, mcp_connections=0, seats=1)


class TestPeriodBounds:
    async def test_a_workspace_with_no_subscription_uses_the_calendar_month(self) -> None:
        # A Free workspace has no billing period of its own; inventing
        # one from its signup date would reset its quota on a day it has
        # no reason to expect.
        fixture = _Fixture()
        start, end = await fixture.usage.current_period_bounds("ws-1")
        assert (start, end) == calendar_month_bounds(_T0)

    async def test_a_subscribed_workspace_uses_its_subscription_period(self) -> None:
        # Subscribed on the 5th, billed the 5th to the 5th. Aggregating
        # by calendar month would split its usage across two invoices.
        fixture = _Fixture()
        await fixture.subscribe(PlanTier.PRO)
        start, end = await fixture.usage.current_period_bounds("ws-1")
        assert start == _T0
        assert end == datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


class TestRecording:
    async def test_recording_the_same_run_twice_writes_once(self) -> None:
        # A worker that crashes after recording and before acknowledging
        # re-runs and re-records; without the key the workspace is billed
        # twice for work done once.
        fixture = _Fixture()
        first = await fixture.usage.record_run(
            workspace_id="ws-1", run_id="run-1", tokens=1200, cost_micro_usd=450
        )
        second = await fixture.usage.record_run(
            workspace_id="ws-1", run_id="run-1", tokens=1200, cost_micro_usd=450
        )
        assert first == 2
        assert second == 0
        usage = await fixture.usage.current_period_usage("ws-1")
        assert usage.quantity(MeteredDimension.AGENT_RUNS) == 1
        assert usage.quantity(MeteredDimension.TOKENS) == 1200

    async def test_a_run_records_both_its_dimensions_together(self) -> None:
        # A run that counted its tokens but not itself would show usage
        # no allowance was consumed by.
        fixture = _Fixture()
        await fixture.usage.record_run(
            workspace_id="ws-1", run_id="run-1", tokens=500, cost_micro_usd=100
        )
        usage = await fixture.usage.current_period_usage("ws-1")
        assert usage.quantity(MeteredDimension.AGENT_RUNS) == 1
        assert usage.cost_micro_usd(MeteredDimension.TOKENS) == 100

    async def test_recording_quietly_swallows_a_failure(self) -> None:
        # A run that finished must not be reported as failed because the
        # usage write hit a constraint — the customer got the work.
        fixture = _Fixture()

        async def explode(events: list[UsageEvent]) -> int:
            raise RuntimeError("database is down")

        fixture.usage_repo.record = explode  # type: ignore[method-assign]
        await fixture.usage.record_quietly(
            [
                UsageEvent(
                    workspace_id="ws-1",
                    dimension=MeteredDimension.AGENT_RUNS,
                    quantity=1,
                    occurred_at=_T0,
                    source=UsageSource.AGENT_RUN,
                    source_id="run-1",
                    idempotency_key="run:run-1:agent_runs",
                )
            ]
        )

    async def test_usage_outside_the_period_is_not_counted(self) -> None:
        fixture = _Fixture()
        await fixture.subscribe(PlanTier.PRO)
        await fixture.use_runs(3, at=_T0 - timedelta(days=1))
        usage = await fixture.usage.current_period_usage("ws-1")
        assert usage.quantity(MeteredDimension.AGENT_RUNS) == 0


class TestQuota:
    async def test_a_workspace_under_its_allowance_is_allowed(self) -> None:
        fixture = _Fixture()
        await fixture.use_runs(10)
        decision = await fixture.quota.check(
            workspace_id="ws-1", dimension=MeteredDimension.AGENT_RUNS
        )
        assert decision.allowed is True
        assert decision.used == 10
        assert decision.remaining == 490

    async def test_a_free_workspace_at_its_limit_is_refused(self) -> None:
        # Free carries no overage rate, so exceeding is a hard stop —
        # which is what makes Free genuinely free.
        fixture = _Fixture()
        await fixture.use_runs(500)
        with pytest.raises(QuotaExceededError) as exc:
            await fixture.quota.enforce(workspace_id="ws-1", dimension=MeteredDimension.AGENT_RUNS)
        assert exc.value.decision.allowance == 500
        assert exc.value.decision.billable_overage is False

    async def test_a_paid_workspace_over_its_allowance_proceeds_and_is_billed(self) -> None:
        # Pro has an overage rate: the customer agreed to pay beyond the
        # allowance, so the request is allowed and produces an invoice
        # line rather than a refusal.
        fixture = _Fixture()
        await fixture.subscribe(PlanTier.PRO)
        await fixture.use_runs(10_000)
        decision = await fixture.quota.enforce(
            workspace_id="ws-1", dimension=MeteredDimension.AGENT_RUNS
        )
        assert decision.allowed is True
        assert decision.billable_overage is True

    async def test_an_unlimited_allowance_never_refuses(self) -> None:
        fixture = _Fixture()
        await fixture.subscribe(PlanTier.TEAM)
        decision = await fixture.quota.check(
            workspace_id="ws-1", dimension=MeteredDimension.AGENT_RUNS, requested=10**9
        )
        assert decision.allowed is True
        assert decision.allowance is None
        assert decision.remaining is None

    async def test_a_bulk_request_is_checked_as_a_whole(self) -> None:
        # Admitting it one unit at a time would let it pass a check it
        # collectively fails.
        fixture = _Fixture()
        await fixture.use_runs(498)
        assert (
            await fixture.quota.check(
                workspace_id="ws-1", dimension=MeteredDimension.AGENT_RUNS, requested=2
            )
        ).allowed is True
        assert (
            await fixture.quota.check(
                workspace_id="ws-1", dimension=MeteredDimension.AGENT_RUNS, requested=3
            )
        ).allowed is False

    async def test_the_refusal_carries_a_reset_time(self) -> None:
        # A customer refused with no reset time cannot tell a quota limit
        # from an outage.
        fixture = _Fixture()
        await fixture.use_runs(500)
        decision = await fixture.quota.check(
            workspace_id="ws-1", dimension=MeteredDimension.AGENT_RUNS
        )
        assert decision.resets_at == calendar_month_bounds(_T0)[1]
        assert decision.retry_after_seconds(_T0) > 1

    async def test_retry_after_is_never_zero(self) -> None:
        # Zero tells a client to retry immediately into the same refusal.
        fixture = _Fixture()
        decision = await fixture.quota.check(
            workspace_id="ws-1", dimension=MeteredDimension.AGENT_RUNS
        )
        assert decision.retry_after_seconds(decision.resets_at) == 1

    async def test_the_quota_uses_the_same_plan_entitlements_resolve(self) -> None:
        # Resolving the plan a second way would let a workspace be
        # quota-checked against one plan and shown another.
        fixture = _Fixture()
        await fixture.subscribe(PlanTier.PRO)
        decision = await fixture.quota.check(
            workspace_id="ws-1", dimension=MeteredDimension.AGENT_RUNS
        )
        entitlements = await fixture.entitlements.entitlements_for("ws-1")
        runs = next(
            line
            for line in entitlements.metered
            if line.dimension == MeteredDimension.AGENT_RUNS.value
        )
        assert decision.allowance == runs.limit


class TestEntitlementsShowRealUsage:
    async def test_metered_lines_reflect_recorded_events(self) -> None:
        fixture = _Fixture()
        await fixture.subscribe(PlanTier.PRO)
        await fixture.use_runs(42)
        entitlements = await fixture.entitlements.entitlements_for("ws-1")
        runs = next(
            line
            for line in entitlements.metered
            if line.dimension == MeteredDimension.AGENT_RUNS.value
        )
        assert runs.used == 42
        assert runs.limit == 10_000


class TestAggregation:
    async def test_aggregating_twice_does_not_double_count(self) -> None:
        # The rollup key is (workspace, period_start, dimension), so a
        # re-run recomputes rather than adding a second total.
        fixture = _Fixture()
        await fixture.subscribe(PlanTier.PRO)
        await fixture.use_runs(7)
        start, end = await fixture.usage.current_period_bounds("ws-1")
        first = await fixture.usage.aggregate_period(
            workspace_id="ws-1", period_start=start, period_end=end
        )
        second = await fixture.usage.aggregate_period(
            workspace_id="ws-1", period_start=start, period_end=end
        )
        assert first.quantity(MeteredDimension.AGENT_RUNS) == 7
        assert second.quantity(MeteredDimension.AGENT_RUNS) == 7

    async def test_an_open_period_cannot_be_finalized(self) -> None:
        # Freezing totals while work is still landing would bill a period
        # in progress.
        fixture = _Fixture()
        await fixture.subscribe(PlanTier.PRO)
        start, end = await fixture.usage.current_period_bounds("ws-1")
        with pytest.raises(ValueError, match="still open"):
            await fixture.usage.finalize_period(
                workspace_id="ws-1", period_start=start, period_end=end
            )

    async def test_finalizing_a_closed_period_freezes_its_totals(self) -> None:
        fixture = _Fixture()
        await fixture.subscribe(PlanTier.PRO)
        await fixture.use_runs(12)
        start, end = await fixture.usage.current_period_bounds("ws-1")
        fixture.clock.advance(days=32)
        await fixture.usage.finalize_period(workspace_id="ws-1", period_start=start, period_end=end)
        stored = await fixture.usage_repo.finalized_rollups(workspace_id="ws-1", period_start=start)
        assert stored is not None
        assert stored.quantity(MeteredDimension.AGENT_RUNS) == 12

    async def test_finalizing_recomputes_rather_than_trusting_the_last_run(self) -> None:
        # `billing-expert`'s reconciliation step: if an incremental
        # rollup and a full recount disagree, the recount is right.
        fixture = _Fixture()
        await fixture.subscribe(PlanTier.PRO)
        await fixture.use_runs(3)
        start, end = await fixture.usage.current_period_bounds("ws-1")
        await fixture.usage.aggregate_period(
            workspace_id="ws-1", period_start=start, period_end=end
        )
        # More usage lands after the incremental rollup.
        await fixture.use_runs(5, at=_T0 + timedelta(days=1))
        fixture.clock.advance(days=32)
        final = await fixture.usage.finalize_period(
            workspace_id="ws-1", period_start=start, period_end=end
        )
        assert final.quantity(MeteredDimension.AGENT_RUNS) == 8


class TestReconciliation:
    async def test_matching_totals_report_no_drift(self) -> None:
        fixture = _Fixture()
        await fixture.subscribe(PlanTier.PRO)
        await fixture.use_runs(4)
        start, end = await fixture.usage.current_period_bounds("ws-1")
        fixture.clock.advance(days=32)
        await fixture.usage.finalize_period(workspace_id="ws-1", period_start=start, period_end=end)
        assert (
            await fixture.usage.reconcile_period(
                workspace_id="ws-1", period_start=start, period_end=end
            )
            == {}
        )

    async def test_an_unfinalized_period_reports_no_drift(self) -> None:
        # Nothing to compare against; reporting drift here would fill the
        # report with every open period.
        fixture = _Fixture()
        await fixture.subscribe(PlanTier.PRO)
        start, end = await fixture.usage.current_period_bounds("ws-1")
        assert (
            await fixture.usage.reconcile_period(
                workspace_id="ws-1", period_start=start, period_end=end
            )
            == {}
        )

    async def test_a_late_event_after_finalization_shows_as_drift(self) -> None:
        # Metering drift is otherwise silent until a customer disputes a
        # charge.
        fixture = _Fixture()
        await fixture.subscribe(PlanTier.PRO)
        await fixture.use_runs(4)
        start, end = await fixture.usage.current_period_bounds("ws-1")
        fixture.clock.advance(days=32)
        await fixture.usage.finalize_period(workspace_id="ws-1", period_start=start, period_end=end)
        await fixture.usage.record(
            [
                UsageEvent(
                    workspace_id="ws-1",
                    dimension=MeteredDimension.AGENT_RUNS,
                    quantity=1,
                    occurred_at=_T0 + timedelta(days=2),
                    source=UsageSource.AGENT_RUN,
                    source_id="late",
                    idempotency_key="run:late:agent_runs",
                )
            ]
        )
        drift = await fixture.usage.reconcile_period(
            workspace_id="ws-1", period_start=start, period_end=end
        )
        assert drift[MeteredDimension.AGENT_RUNS] == (4, 5)


class TestInvoicing:
    async def test_a_preview_reflects_live_usage(self) -> None:
        # The no-surprise-billing rule: the overage a customer will owe is
        # visible before the invoice, not discovered on it.
        fixture = _Fixture()
        await fixture.subscribe(PlanTier.PRO)
        await fixture.use_runs(12_000)
        invoice = await fixture.invoicing.preview_current_period("ws-1")
        assert invoice.has_overage is True
        # 2,000 over -> 2 increments at 300c, plus the 2900c plan fee.
        assert invoice.subtotal_cents == 3500

    async def test_a_free_workspace_previews_a_zero_invoice(self) -> None:
        fixture = _Fixture()
        await fixture.use_runs(100)
        invoice = await fixture.invoicing.preview_current_period("ws-1")
        assert invoice.subtotal_cents == 0
        assert invoice.has_overage is False

    async def test_issuing_refuses_an_unfinalized_period(self) -> None:
        # An invoice built from a period still accepting usage would
        # change between being shown and being paid.
        fixture = _Fixture()
        await fixture.subscribe(PlanTier.PRO)
        start, _ = await fixture.usage.current_period_bounds("ws-1")
        with pytest.raises(PeriodNotFinalizedError):
            await fixture.invoicing.issue_for_period(workspace_id="ws-1", period_start=start)

    async def test_issuing_uses_the_frozen_totals_not_live_events(self) -> None:
        # An issued invoice must not change because a late event arrived.
        fixture = _Fixture()
        await fixture.subscribe(PlanTier.PRO)
        await fixture.use_runs(12_000)
        start, end = await fixture.usage.current_period_bounds("ws-1")
        fixture.clock.advance(days=32)
        await fixture.usage.finalize_period(workspace_id="ws-1", period_start=start, period_end=end)
        issued = await fixture.invoicing.issue_for_period(workspace_id="ws-1", period_start=start)
        # A late event lands after the invoice was issued.
        await fixture.usage.record(
            [
                UsageEvent(
                    workspace_id="ws-1",
                    dimension=MeteredDimension.AGENT_RUNS,
                    quantity=5_000,
                    occurred_at=_T0 + timedelta(days=3),
                    source=UsageSource.AGENT_RUN,
                    source_id="late",
                    idempotency_key="run:late:agent_runs",
                )
            ]
        )
        reissued = await fixture.invoicing.issue_for_period(workspace_id="ws-1", period_start=start)
        assert reissued.subtotal_cents == issued.subtotal_cents == 3500
