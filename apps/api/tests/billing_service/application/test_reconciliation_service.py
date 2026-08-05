"""Drift detection between this system's projection and the provider.

Every case here is silent in production: none of them raises, logs an
error, or shows up in a dashboard. That is exactly why the comparison
exists, and why the tests enumerate the shapes rather than spot-checking
one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agentverse_api.billing_service.application.reconciliation_service import (
    DiscrepancyKind,
    ReconciliationService,
)
from agentverse_api.billing_service.domain.payment_provider import (
    ProviderError,
    ProviderSubscriptionState,
)
from agentverse_api.billing_service.domain.plan import BillingInterval, PlanTier
from agentverse_api.billing_service.domain.subscription import (
    Subscription,
    SubscriptionStatus,
)
from tests.billing_service.fakes import FakePaymentProvider, FakeSubscriptionRepository

_T0 = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


class _OneSubscriptionRepo(FakeSubscriptionRepository):
    """Holds one hand-built subscription, so a test can assert against a
    state the service's own transitions could not easily produce.
    """

    def __init__(self, subscription: Subscription | None) -> None:
        super().__init__()
        self._only = subscription

    async def get_for_workspace(self, workspace_id: str) -> Subscription | None:
        del workspace_id
        return self._only


def _subscription(
    *,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
    provider_subscription_id: str | None = "sub_1",
    cancel_at_period_end: bool = False,
    plan_slug: PlanTier = PlanTier.PRO,
    period_end: datetime | None = None,
) -> Subscription:
    return Subscription(
        id="sub-local",
        workspace_id="ws-1",
        plan_id="plan-pro",
        plan_slug=plan_slug,
        status=status,
        interval=BillingInterval.MONTHLY,
        current_period_start=_T0,
        current_period_end=period_end or (_T0 + timedelta(days=30)),
        trial_end=None,
        cancel_at_period_end=cancel_at_period_end,
        canceled_at=None,
        past_due_since=None,
        provider_subscription_id=provider_subscription_id,
        created_at=_T0,
        updated_at=_T0,
    )


def _remote(
    *,
    status: str = "active",
    cancel_at_period_end: bool = False,
    period_end: datetime | None = None,
) -> ProviderSubscriptionState:
    return ProviderSubscriptionState(
        id="sub_1",
        status=status,
        current_period_start=_T0,
        current_period_end=period_end or (_T0 + timedelta(days=30)),
        cancel_at_period_end=cancel_at_period_end,
        canceled_at=None,
    )


def _service(
    subscription: Subscription | None, remote: ProviderSubscriptionState | None
) -> tuple[ReconciliationService, FakePaymentProvider]:
    provider = FakePaymentProvider()
    if remote is not None:
        provider.subscription_states["sub_1"] = remote
    return (
        ReconciliationService(provider=provider, subscriptions=_OneSubscriptionRepo(subscription)),
        provider,
    )


class TestClean:
    async def test_matching_state_reports_nothing(self) -> None:
        service, _ = _service(_subscription(), _remote())
        assert await service.reconcile_workspace("ws-1") == []

    async def test_a_workspace_with_no_subscription_reports_nothing(self) -> None:
        service, _ = _service(None, None)
        assert await service.reconcile_workspace("ws-1") == []

    async def test_a_days_period_difference_is_within_tolerance(self) -> None:
        # The two clocks advance a period at slightly different moments;
        # flagging that would report every renewal as a finding.
        service, _ = _service(
            _subscription(), _remote(period_end=_T0 + timedelta(days=30, hours=6))
        )
        assert await service.reconcile_workspace("ws-1") == []


class TestFindings:
    async def test_a_subscription_the_provider_has_never_heard_of(self) -> None:
        # The workspace is being served and not billed.
        service, _ = _service(_subscription(), None)
        found = await service.reconcile_workspace("ws-1")
        assert [f.kind for f in found] == [DiscrepancyKind.MISSING_AT_PROVIDER]

    async def test_live_here_and_dead_there(self) -> None:
        service, _ = _service(_subscription(), _remote(status="canceled"))
        found = await service.reconcile_workspace("ws-1")
        assert DiscrepancyKind.STATUS_MISMATCH in [f.kind for f in found]

    async def test_past_due_is_not_a_mismatch_with_active(self) -> None:
        # Both sides consider a past-due subscription live; treating the
        # vocabulary difference as drift would bury the real findings.
        service, _ = _service(
            _subscription(status=SubscriptionStatus.PAST_DUE), _remote(status="past_due")
        )
        assert await service.reconcile_workspace("ws-1") == []

    async def test_a_cancellation_recorded_on_one_side_only(self) -> None:
        # It will end on one side and renew on the other.
        service, _ = _service(
            _subscription(cancel_at_period_end=True), _remote(cancel_at_period_end=False)
        )
        found = await service.reconcile_workspace("ws-1")
        assert [f.kind for f in found] == [DiscrepancyKind.CANCELLATION_MISMATCH]

    async def test_periods_that_disagree_by_more_than_a_day(self) -> None:
        # Usage would be aggregated into the wrong invoice.
        service, _ = _service(_subscription(), _remote(period_end=_T0 + timedelta(days=45)))
        found = await service.reconcile_workspace("ws-1")
        assert [f.kind for f in found] == [DiscrepancyKind.PERIOD_DRIFT]

    async def test_a_paid_plan_with_no_provider_link(self) -> None:
        # Nothing is charging for it.
        service, _ = _service(_subscription(provider_subscription_id=None), None)
        found = await service.reconcile_workspace("ws-1")
        assert [f.kind for f in found] == [DiscrepancyKind.UNLINKED]

    async def test_a_free_plan_with_no_provider_link_is_expected(self) -> None:
        service, _ = _service(
            _subscription(provider_subscription_id=None, plan_slug=PlanTier.FREE), None
        )
        assert await service.reconcile_workspace("ws-1") == []

    async def test_findings_carry_both_sides_verbatim(self) -> None:
        # So the finding can be acted on without re-running the
        # comparison.
        service, _ = _service(_subscription(), _remote(status="canceled"))
        found = await service.reconcile_workspace("ws-1")
        assert found[0].local == "active"
        assert found[0].remote == "canceled"


class TestProviderOutage:
    async def test_an_unreachable_provider_is_not_a_discrepancy(self) -> None:
        # Reporting one would fill the report with noise on exactly the
        # day it matters least.
        service, provider = _service(_subscription(), _remote())
        provider.fail_with = ProviderError("provider down", retryable=True)
        assert await service.reconcile_workspace("ws-1") == []


class TestNoAutoRepair:
    async def test_reconciliation_never_writes(self) -> None:
        # A bug in the comparison must not be able to cancel paying
        # customers in bulk. It reports; a human decides.
        subscription = _subscription()
        repo = _OneSubscriptionRepo(subscription)
        provider = FakePaymentProvider()
        provider.subscription_states["sub_1"] = _remote(status="canceled")
        service = ReconciliationService(provider=provider, subscriptions=repo)
        await service.reconcile_workspace("ws-1")
        assert repo.events == []
        assert await repo.get_for_workspace("ws-1") == subscription
        assert not provider.called("cancel_subscription")
