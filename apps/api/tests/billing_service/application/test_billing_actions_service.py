"""The money-moving actions, against a recording fake provider.

The central assertion in several of these is **ordering**: the provider
is called before this system's own state changes. If that inverts, a
failed provider call leaves a customer marked canceled here and still
charged there, and nothing detects it until they complain.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agentverse_api.billing_service.application.billing_actions_service import (
    BillingActionsService,
)
from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.application.subscription_service import SubscriptionService
from agentverse_api.billing_service.domain.customer import PaymentProvider
from agentverse_api.billing_service.domain.exceptions import (
    PlanNotPurchasableError,
    SubscriptionAlreadyExistsError,
    SubscriptionNotFoundError,
)
from agentverse_api.billing_service.domain.payment_provider import (
    ProviderError,
    ProviderInvoice,
    ProviderPaymentMethod,
)
from agentverse_api.billing_service.domain.plan import (
    BillingInterval,
    Capability,
    Plan,
    PlanTier,
)
from tests.billing_service.fakes import (
    FakeCustomerRepository,
    FakePaymentProvider,
    FakePlanRepository,
    FakeSubscriptionRepository,
)

_T0 = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


def _plan(slug: PlanTier, *, monthly: int | None, annual: int | None = None) -> Plan:
    return Plan(
        id=f"plan-{slug.value}",
        slug=slug,
        display_name=slug.value.title(),
        description="",
        monthly_price_cents=monthly,
        annual_price_cents=annual,
        currency="usd",
        trial_days=14 if monthly else 0,
        is_public=True,
        is_active=True,
        sort_order=0,
        resource_limits={},
        metered_allowances={},
        capabilities=frozenset({Capability.COMMUNITY_SUPPORT}),
        overage_rates={},
    )


_PLANS = [
    _plan(PlanTier.FREE, monthly=0, annual=0),
    _plan(PlanTier.PRO, monthly=2900, annual=29000),
    _plan(PlanTier.TEAM, monthly=9900, annual=99000),
    _plan(PlanTier.ENTERPRISE, monthly=None, annual=None),
]


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now


def _service() -> tuple[
    BillingActionsService, FakePaymentProvider, SubscriptionService, FakeCustomerRepository
]:
    repo = FakeSubscriptionRepository()
    for plan in _PLANS:
        repo.seed_plan(plan.id, plan.slug)
    customers = FakeCustomerRepository()
    catalog = PlanCatalogService(plans=FakePlanRepository(_PLANS))
    subscriptions = SubscriptionService(
        subscriptions=repo, customers=customers, catalog=catalog, now=_Clock(_T0)
    )
    provider = FakePaymentProvider()
    return (
        BillingActionsService(
            provider=provider,
            subscriptions=subscriptions,
            customers=customers,
            catalog=catalog,
        ),
        provider,
        subscriptions,
        customers,
    )


async def _subscribe(subscriptions: SubscriptionService, *, slug: PlanTier = PlanTier.PRO):
    return await subscriptions.start(
        workspace_id="ws-1",
        plan_slug=slug,
        interval=BillingInterval.MONTHLY,
        actor="user-1",
        idempotency_key="start-1",
        with_trial=False,
        provider_subscription_id="sub_1",
    )


class TestCheckout:
    async def test_it_returns_a_hosted_url_and_creates_no_subscription(self) -> None:
        # A subscription created optimistically here would be a phantom
        # for every customer who opened checkout and closed the tab.
        service, provider, subscriptions, _ = _service()
        session = await service.start_checkout(
            workspace_id="ws-1",
            plan_slug=PlanTier.PRO,
            interval=BillingInterval.MONTHLY,
            success_url="/ok",
            cancel_url="/no",
            billing_email=None,
            workspace_name=None,
        )
        assert session.url.startswith("https://")
        assert await subscriptions.current("ws-1") is None
        assert provider.called("create_checkout_session")

    async def test_the_customer_is_linked_before_checkout_starts(self) -> None:
        # Without the link, the webhook that follows has nothing to
        # attach the subscription to.
        service, _, _, customers = _service()
        await service.start_checkout(
            workspace_id="ws-1",
            plan_slug=PlanTier.PRO,
            interval=BillingInterval.MONTHLY,
            success_url="/ok",
            cancel_url="/no",
            billing_email="finance@example.test",
            workspace_name="Acme",
        )
        linked = await customers.get_for_workspace("ws-1")
        assert linked is not None
        assert linked.provider_customer_id == "cus_fake"

    async def test_an_existing_subscription_blocks_a_second_checkout(self) -> None:
        service, _, subscriptions, _ = _service()
        await _subscribe(subscriptions)
        with pytest.raises(SubscriptionAlreadyExistsError):
            await service.start_checkout(
                workspace_id="ws-1",
                plan_slug=PlanTier.TEAM,
                interval=BillingInterval.MONTHLY,
                success_url="/ok",
                cancel_url="/no",
                billing_email=None,
                workspace_name=None,
            )

    async def test_enterprise_cannot_be_checked_out(self) -> None:
        service, _, _, _ = _service()
        with pytest.raises(PlanNotPurchasableError):
            await service.start_checkout(
                workspace_id="ws-1",
                plan_slug=PlanTier.ENTERPRISE,
                interval=BillingInterval.MONTHLY,
                success_url="/ok",
                cancel_url="/no",
                billing_email=None,
                workspace_name=None,
            )

    async def test_the_plans_trial_length_is_passed_through(self) -> None:
        # Not re-decided at the provider: the catalog owns it (Rule 3).
        service, provider, _, _ = _service()
        await service.start_checkout(
            workspace_id="ws-1",
            plan_slug=PlanTier.PRO,
            interval=BillingInterval.MONTHLY,
            success_url="/ok",
            cancel_url="/no",
            billing_email=None,
            workspace_name=None,
        )
        call = next(c for c in provider.calls if c.method == "create_checkout_session")
        assert call.kwargs["trial_days"] == 14


class TestPortal:
    async def test_it_needs_a_linked_customer(self) -> None:
        service, _, _, _ = _service()
        with pytest.raises(SubscriptionNotFoundError):
            await service.open_portal(workspace_id="ws-1", return_url="/back")

    async def test_it_returns_the_provider_url(self) -> None:
        service, _, _, customers = _service()
        await customers.upsert(
            workspace_id="ws-1",
            provider=PaymentProvider.STRIPE,
            provider_customer_id="cus_1",
            billing_email=None,
        )
        session = await service.open_portal(workspace_id="ws-1", return_url="/back")
        assert session.url.startswith("https://")


class TestOrdering:
    async def test_a_failed_provider_cancel_leaves_local_state_untouched(self) -> None:
        # The whole reason the provider is called first. If this
        # inverted, the customer would be marked canceled here and still
        # charged there.
        service, provider, subscriptions, _ = _service()
        await _subscribe(subscriptions)
        provider.fail_with = ProviderError("provider down", retryable=True)
        with pytest.raises(ProviderError):
            await service.cancel(workspace_id="ws-1", actor="user-1", at_period_end=True)
        subscription = await subscriptions.current("ws-1")
        assert subscription is not None
        assert subscription.cancel_at_period_end is False

    async def test_a_failed_provider_plan_change_leaves_local_state_untouched(self) -> None:
        service, provider, subscriptions, _ = _service()
        await _subscribe(subscriptions)
        provider.fail_with = ProviderError("provider down", retryable=True)
        with pytest.raises(ProviderError):
            await service.change_plan(
                workspace_id="ws-1",
                target_slug=PlanTier.TEAM,
                interval=BillingInterval.MONTHLY,
                actor="user-1",
                idempotency_key="change-1",
            )
        subscription = await subscriptions.current("ws-1")
        assert subscription is not None
        assert subscription.plan_slug is PlanTier.PRO


class TestSubscriptionMutations:
    async def test_cancel_calls_the_provider_and_records_the_intent(self) -> None:
        service, provider, subscriptions, _ = _service()
        await _subscribe(subscriptions)
        result = await service.cancel(workspace_id="ws-1", actor="user-1", at_period_end=True)
        assert provider.called("cancel_subscription")
        assert result.cancel_at_period_end is True
        # Still entitled: they paid for this period.
        assert result.entitles is True

    async def test_resume_undoes_a_scheduled_cancellation(self) -> None:
        service, provider, subscriptions, _ = _service()
        await _subscribe(subscriptions)
        await service.cancel(workspace_id="ws-1", actor="user-1", at_period_end=True)
        result = await service.resume(workspace_id="ws-1")
        assert provider.called("resume_subscription")
        assert result.cancel_at_period_end is False

    async def test_pause_and_unpause_both_reach_the_provider(self) -> None:
        # A local-only pause would stop serving the customer while the
        # provider kept charging them.
        service, provider, subscriptions, _ = _service()
        await _subscribe(subscriptions)
        await service.pause(workspace_id="ws-1", actor="user-1")
        assert provider.called("pause_subscription")
        await service.unpause(workspace_id="ws-1", actor="user-1")
        assert provider.called("unpause_subscription")

    async def test_a_plan_change_moves_the_provider_then_this_system(self) -> None:
        service, provider, subscriptions, _ = _service()
        await _subscribe(subscriptions)
        subscription, proration = await service.change_plan(
            workspace_id="ws-1",
            target_slug=PlanTier.TEAM,
            interval=BillingInterval.MONTHLY,
            actor="user-1",
            idempotency_key="change-1",
        )
        assert provider.called("change_subscription_plan")
        assert subscription.plan_slug is PlanTier.TEAM
        # Changed at the very start of the period: the whole period
        # prorates, so the customer is credited Pro and charged Team.
        assert proration.unused_credit_cents == 2900
        assert proration.prorated_charge_cents == 9900


class TestQuote:
    async def test_it_prices_the_change_without_making_it(self) -> None:
        # A customer should never first learn a proration figure from
        # their statement.
        service, provider, subscriptions, _ = _service()
        await _subscribe(subscriptions)
        quote = await service.quote_plan_change(
            workspace_id="ws-1", target_slug=PlanTier.TEAM, interval=BillingInterval.MONTHLY
        )
        assert quote.is_upgrade is True
        assert quote.proration.net_cents == 7000
        assert not provider.called("change_subscription_plan")
        subscription = await subscriptions.current("ws-1")
        assert subscription is not None
        assert subscription.plan_slug is PlanTier.PRO

    async def test_a_downgrade_quote_is_negative(self) -> None:
        service, _, subscriptions, _ = _service()
        await _subscribe(subscriptions, slug=PlanTier.TEAM)
        quote = await service.quote_plan_change(
            workspace_id="ws-1", target_slug=PlanTier.PRO, interval=BillingInterval.MONTHLY
        )
        assert quote.is_upgrade is False
        assert quote.proration.net_cents < 0

    async def test_quoting_enterprise_is_refused(self) -> None:
        service, _, subscriptions, _ = _service()
        await _subscribe(subscriptions)
        with pytest.raises(PlanNotPurchasableError):
            await service.quote_plan_change(
                workspace_id="ws-1",
                target_slug=PlanTier.ENTERPRISE,
                interval=BillingInterval.MONTHLY,
            )


class TestReads:
    async def test_invoices_are_empty_for_a_workspace_that_never_paid(self) -> None:
        # The invoice table should render its empty state, not an error.
        service, _, _, _ = _service()
        assert await service.list_invoices(workspace_id="ws-1") == []

    async def test_invoices_come_from_the_provider(self) -> None:
        service, provider, _, customers = _service()
        await customers.upsert(
            workspace_id="ws-1",
            provider=PaymentProvider.STRIPE,
            provider_customer_id="cus_1",
            billing_email=None,
        )
        provider.invoices = [
            ProviderInvoice(
                id="in_1",
                number="AV-0001",
                status="paid",
                amount_due_cents=2900,
                amount_paid_cents=2900,
                currency="usd",
                created_at=_T0,
                period_start=None,
                period_end=None,
                hosted_invoice_url="https://provider.test/i/in_1",
                invoice_pdf_url=None,
            )
        ]
        invoices = await service.list_invoices(workspace_id="ws-1")
        assert [invoice.id for invoice in invoices] == ["in_1"]

    async def test_payment_methods_carry_no_sensitive_card_data(self) -> None:
        # Brand, last four and expiry are the only card-derived values
        # this system ever holds, and it holds them transiently.
        service, provider, _, customers = _service()
        await customers.upsert(
            workspace_id="ws-1",
            provider=PaymentProvider.STRIPE,
            provider_customer_id="cus_1",
            billing_email=None,
        )
        provider.payment_methods = [
            ProviderPaymentMethod(
                id="pm_1",
                brand="visa",
                last4="4242",
                exp_month=12,
                exp_year=2030,
                is_default=True,
            )
        ]
        methods = await service.list_payment_methods(workspace_id="ws-1")
        assert methods[0].last4 == "4242"
        fields = set(vars(type(methods[0])).get("__slots__", ()))
        assert not fields & {"number", "cvc", "pan"}


class TestRefund:
    async def test_an_invoice_from_another_workspace_cannot_be_refunded(self) -> None:
        # Without the ownership check, an invoice id from another tenant
        # would refund their charge (Rule 11). Refused without confirming
        # the invoice exists elsewhere.
        service, provider, _, customers = _service()
        await customers.upsert(
            workspace_id="ws-1",
            provider=PaymentProvider.STRIPE,
            provider_customer_id="cus_1",
            billing_email=None,
        )
        provider.invoices = []
        with pytest.raises(ProviderError):
            await service.refund(
                workspace_id="ws-1",
                invoice_id="in_someone_else",
                amount_cents=None,
                reason=None,
            )
        assert not provider.called("refund_payment")

    async def test_a_workspace_invoice_can_be_refunded(self) -> None:
        service, provider, _, customers = _service()
        await customers.upsert(
            workspace_id="ws-1",
            provider=PaymentProvider.STRIPE,
            provider_customer_id="cus_1",
            billing_email=None,
        )
        provider.invoices = [
            ProviderInvoice(
                id="in_1",
                number=None,
                status="paid",
                amount_due_cents=2900,
                amount_paid_cents=2900,
                currency="usd",
                created_at=_T0,
                period_start=None,
                period_end=None,
                hosted_invoice_url=None,
                invoice_pdf_url=None,
            )
        ]
        refund_id = await service.refund(
            workspace_id="ws-1", invoice_id="in_1", amount_cents=1000, reason="goodwill"
        )
        assert refund_id == "re_fake"
        call = next(c for c in provider.calls if c.method == "refund_payment")
        assert call.kwargs["amount_cents"] == 1000

    async def test_a_refund_needs_a_billing_account(self) -> None:
        service, _, _, _ = _service()
        with pytest.raises(SubscriptionNotFoundError):
            await service.refund(
                workspace_id="ws-1", invoice_id="in_1", amount_cents=None, reason=None
            )
