"""In-memory implementations of the billing ports.

Shared rather than redefined per test module (CLAUDE.md §11: "shared
fakes from `tests/fakes/`"). The subscription fake carries real
behaviour, not stubs — the partial-unique-index rule, the
idempotency-key rejection, and the mutable-field allowlist are all
enforced here, so a unit test that passes against the fake is testing
the same contract the Postgres adapter implements rather than a weaker
one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from agentverse_api.billing_service.domain.customer import BillingCustomer, PaymentProvider
from agentverse_api.billing_service.domain.entitlements import ResourceUsage
from agentverse_api.billing_service.domain.payment_provider import (
    CheckoutSession,
    PortalSession,
    ProviderEvent,
    ProviderInvoice,
    ProviderPaymentMethod,
    ProviderSubscriptionState,
)
from agentverse_api.billing_service.domain.plan import BillingInterval, Plan, PlanTier
from agentverse_api.billing_service.domain.subscription import (
    Subscription,
    SubscriptionStatus,
    SubscriptionTrigger,
)

_MUTABLE_ON_TRANSITION = frozenset(
    {
        "current_period_start",
        "current_period_end",
        "trial_end",
        "cancel_at_period_end",
        "canceled_at",
        "past_due_since",
        "provider_subscription_id",
    }
)


class FakePlanRepository:
    def __init__(self, plans: list[Plan]) -> None:
        self._plans = plans

    async def list_active(self, *, public_only: bool) -> list[Plan]:
        return [
            plan for plan in self._plans if plan.is_active and (plan.is_public or not public_only)
        ]

    async def get_by_slug(self, slug: PlanTier) -> Plan | None:
        for plan in self._plans:
            if plan.slug is slug and plan.is_active:
                return plan
        return None


class FakeUsageRepository:
    def __init__(self, usage: ResourceUsage) -> None:
        self._usage = usage
        self.calls = 0

    async def resource_usage(self, workspace_id: str) -> ResourceUsage:
        del workspace_id
        self.calls += 1
        return self._usage


@dataclass
class _Event:
    subscription_id: str
    trigger: str
    from_status: str
    to_status: str
    actor: str
    occurred_at: datetime
    #: Kept, not discarded: for a plan change this holds the proration
    #: the service computed, and the event row is its only durable copy.
    metadata: dict[str, object]


class FakeSubscriptionRepository:
    """Mirrors the Postgres adapter's guarantees, including its refusals."""

    def __init__(self) -> None:
        self.rows: dict[str, Subscription] = {}
        self.events: list[_Event] = []
        self._keys: dict[str, str] = {}
        self._plan_slugs: dict[str, PlanTier] = {}

    def seed_plan(self, plan_id: str, slug: PlanTier) -> None:
        """Teach the fake which slug a plan id maps to, so `change_plan`
        can return a subscription whose `plan_slug` is consistent with
        its `plan_id` — the join the real adapter does.
        """
        self._plan_slugs[plan_id] = slug

    async def get_for_workspace(self, workspace_id: str) -> Subscription | None:
        for row in self.rows.values():
            if row.workspace_id == workspace_id and row.status is not SubscriptionStatus.CANCELED:
                return row
        return None

    async def get_by_id(self, subscription_id: str) -> Subscription | None:
        return self.rows.get(subscription_id)

    async def create(
        self,
        *,
        workspace_id: str,
        plan_id: str,
        status: SubscriptionStatus,
        interval: BillingInterval,
        current_period_start: datetime,
        current_period_end: datetime,
        trial_end: datetime | None,
        provider_subscription_id: str | None,
        idempotency_key: str,
        actor: str,
    ) -> Subscription:
        if await self.get_for_workspace(workspace_id) is not None:
            # The partial unique index, in Python. Without this the fake
            # would happily hold two live subscriptions and the unit
            # tests would prove less than the schema does.
            raise ValueError("workspace already has a live subscription")
        subscription_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        row = Subscription(
            id=subscription_id,
            workspace_id=workspace_id,
            plan_id=plan_id,
            plan_slug=self._plan_slugs.get(plan_id, PlanTier.FREE),
            status=status,
            interval=interval,
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            trial_end=trial_end,
            cancel_at_period_end=False,
            canceled_at=None,
            past_due_since=None,
            provider_subscription_id=provider_subscription_id,
            created_at=now,
            updated_at=now,
        )
        self.rows[subscription_id] = row
        self._keys[idempotency_key] = subscription_id
        self.events.append(
            _Event(
                subscription_id=subscription_id,
                trigger=(
                    SubscriptionTrigger.TRIAL_STARTED.value
                    if status is SubscriptionStatus.TRIALING
                    else SubscriptionTrigger.PAYMENT_SUCCEEDED.value
                ),
                from_status=status.value,
                to_status=status.value,
                actor=actor,
                occurred_at=now,
                metadata={"plan_id": plan_id, "interval": interval.value},
            )
        )
        return row

    async def record_transition(
        self,
        *,
        subscription_id: str,
        trigger: SubscriptionTrigger,
        from_status: SubscriptionStatus,
        to_status: SubscriptionStatus,
        idempotency_key: str,
        actor: str,
        reason: str | None,
        metadata: dict[str, object],
        changes: dict[str, object],
    ) -> Subscription:
        del reason
        if idempotency_key in self._keys:
            raise ValueError(f"duplicate idempotency key {idempotency_key!r}")
        unknown = set(changes) - _MUTABLE_ON_TRANSITION
        if unknown:
            raise KeyError(f"not writable on a transition: {sorted(unknown)}")
        row = self.rows[subscription_id]
        updated = replace(row, status=to_status, updated_at=datetime.now(UTC), **changes)
        self.rows[subscription_id] = updated
        self._keys[idempotency_key] = subscription_id
        self.events.append(
            _Event(
                subscription_id=subscription_id,
                trigger=trigger.value,
                from_status=from_status.value,
                to_status=to_status.value,
                actor=actor,
                occurred_at=datetime.now(UTC),
                metadata=metadata,
            )
        )
        return updated

    async def set_cancel_at_period_end(
        self, *, subscription_id: str, cancel_at_period_end: bool
    ) -> Subscription:
        row = self.rows[subscription_id]
        updated = replace(row, cancel_at_period_end=cancel_at_period_end)
        self.rows[subscription_id] = updated
        return updated

    async def change_plan(
        self, *, subscription_id: str, plan_id: str, interval: BillingInterval
    ) -> Subscription:
        row = self.rows[subscription_id]
        updated = replace(
            row,
            plan_id=plan_id,
            plan_slug=self._plan_slugs.get(plan_id, row.plan_slug),
            interval=interval,
        )
        self.rows[subscription_id] = updated
        return updated

    async def find_event_by_idempotency_key(self, key: str) -> str | None:
        return self._keys.get(key)

    async def list_events(
        self, *, subscription_id: str, limit: int
    ) -> list[tuple[str, str, str, str, datetime]]:
        matching = [
            (e.trigger, e.from_status, e.to_status, e.actor, e.occurred_at)
            for e in self.events
            if e.subscription_id == subscription_id
        ]
        matching.reverse()
        return matching[:limit]


class FakeWebhookEventRepository:
    """Enforces the unique-index behaviour the real table has: a second
    claim on the same `(provider, event_id)` loses.
    """

    def __init__(self) -> None:
        self.claimed: dict[tuple[str, str], str] = {}
        self.errors: dict[tuple[str, str], str | None] = {}

    async def claim(
        self,
        *,
        provider: str,
        provider_event_id: str,
        event_type: str,
        workspace_id: str | None,
    ) -> bool:
        del event_type, workspace_id
        key = (provider, provider_event_id)
        if key in self.claimed:
            return False
        self.claimed[key] = "received"
        return True

    async def resolve(
        self, *, provider: str, provider_event_id: str, status: str, error: str | None
    ) -> None:
        key = (provider, provider_event_id)
        self.claimed[key] = status
        self.errors[key] = error

    async def was_processed(self, *, provider: str, provider_event_id: str) -> bool:
        return self.claimed.get((provider, provider_event_id)) in ("processed", "ignored")


@dataclass
class _ProviderCall:
    method: str
    kwargs: dict[str, object]


class FakePaymentProvider:
    """A recording stand-in for `PaymentProviderPort`.

    Records every call so tests can assert *ordering* — specifically that
    the provider is called before this system's own state changes, which
    is the rule that keeps a failed provider call from leaving a customer
    marked canceled here and still charged there.
    """

    def __init__(self) -> None:
        self.calls: list[_ProviderCall] = []
        self.invoices: list[ProviderInvoice] = []
        self.payment_methods: list[ProviderPaymentMethod] = []
        self.subscription_states: dict[str, ProviderSubscriptionState] = {}
        self.verified_event: ProviderEvent | None = None
        self.fail_with: Exception | None = None
        self.next_customer_id = "cus_fake"

    def _record(self, method: str, **kwargs: object) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.calls.append(_ProviderCall(method=method, kwargs=kwargs))

    def called(self, method: str) -> bool:
        return any(call.method == method for call in self.calls)

    async def ensure_customer(
        self, *, workspace_id: str, email: str | None, name: str | None
    ) -> str:
        self._record("ensure_customer", workspace_id=workspace_id, email=email, name=name)
        return self.next_customer_id

    async def create_checkout_session(
        self,
        *,
        workspace_id: str,
        provider_customer_id: str,
        plan_slug: PlanTier,
        interval: BillingInterval,
        success_url: str,
        cancel_url: str,
        trial_days: int | None,
        coupon_code: str | None,
    ) -> CheckoutSession:
        self._record(
            "create_checkout_session",
            workspace_id=workspace_id,
            plan_slug=plan_slug,
            interval=interval,
            trial_days=trial_days,
            coupon_code=coupon_code,
        )
        return CheckoutSession(session_id="cs_fake", url="https://provider.test/checkout/cs_fake")

    async def create_portal_session(
        self, *, provider_customer_id: str, return_url: str
    ) -> PortalSession:
        self._record(
            "create_portal_session",
            provider_customer_id=provider_customer_id,
            return_url=return_url,
        )
        return PortalSession(url="https://provider.test/portal")

    async def cancel_subscription(
        self, *, provider_subscription_id: str, at_period_end: bool
    ) -> None:
        self._record(
            "cancel_subscription",
            provider_subscription_id=provider_subscription_id,
            at_period_end=at_period_end,
        )

    async def resume_subscription(self, *, provider_subscription_id: str) -> None:
        self._record("resume_subscription", provider_subscription_id=provider_subscription_id)

    async def pause_subscription(self, *, provider_subscription_id: str) -> None:
        self._record("pause_subscription", provider_subscription_id=provider_subscription_id)

    async def unpause_subscription(self, *, provider_subscription_id: str) -> None:
        self._record("unpause_subscription", provider_subscription_id=provider_subscription_id)

    async def change_subscription_plan(
        self,
        *,
        provider_subscription_id: str,
        plan_slug: PlanTier,
        interval: BillingInterval,
    ) -> None:
        self._record(
            "change_subscription_plan",
            provider_subscription_id=provider_subscription_id,
            plan_slug=plan_slug,
            interval=interval,
        )

    async def list_invoices(
        self, *, provider_customer_id: str, limit: int
    ) -> list[ProviderInvoice]:
        self._record("list_invoices", provider_customer_id=provider_customer_id, limit=limit)
        return self.invoices

    async def list_payment_methods(
        self, *, provider_customer_id: str
    ) -> list[ProviderPaymentMethod]:
        self._record("list_payment_methods", provider_customer_id=provider_customer_id)
        return self.payment_methods

    async def refund_payment(
        self, *, provider_invoice_id: str, amount_cents: int | None, reason: str | None
    ) -> str:
        self._record(
            "refund_payment",
            provider_invoice_id=provider_invoice_id,
            amount_cents=amount_cents,
            reason=reason,
        )
        return "re_fake"

    async def get_subscription_state(
        self, *, provider_subscription_id: str
    ) -> ProviderSubscriptionState | None:
        self._record("get_subscription_state", provider_subscription_id=provider_subscription_id)
        return self.subscription_states.get(provider_subscription_id)

    def verify_webhook(self, *, payload: bytes, signature: str) -> ProviderEvent | None:
        del payload, signature
        return self.verified_event


class FakeCustomerRepository:
    def __init__(self) -> None:
        self.rows: dict[str, BillingCustomer] = {}

    async def get_for_workspace(self, workspace_id: str) -> BillingCustomer | None:
        return self.rows.get(workspace_id)

    async def upsert(
        self,
        *,
        workspace_id: str,
        provider: PaymentProvider,
        provider_customer_id: str,
        billing_email: str | None,
    ) -> BillingCustomer:
        now = datetime.now(UTC)
        existing = self.rows.get(workspace_id)
        row = BillingCustomer(
            id=existing.id if existing else str(uuid.uuid4()),
            workspace_id=workspace_id,
            provider=provider,
            provider_customer_id=provider_customer_id,
            billing_email=billing_email,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self.rows[workspace_id] = row
        return row
