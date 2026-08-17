"""Repository ports for the billing context.

`infrastructure/repositories.py` implements these against Postgres;
`tests/` implements them in memory. Application-layer use cases depend
only on what is declared here (CLAUDE.md §5).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from agentverse_api.billing_service.domain.coupon import Coupon
from agentverse_api.billing_service.domain.credit import CreditReason, CreditTransaction
from agentverse_api.billing_service.domain.customer import BillingCustomer, PaymentProvider
from agentverse_api.billing_service.domain.entitlements import ResourceUsage
from agentverse_api.billing_service.domain.plan import BillingInterval, Plan, PlanTier
from agentverse_api.billing_service.domain.referral import Referral, ReferralStatus
from agentverse_api.billing_service.domain.subscription import (
    Subscription,
    SubscriptionStatus,
    SubscriptionTrigger,
)
from agentverse_api.billing_service.domain.usage import PeriodUsage, UsageEvent


class PlanRepository(Protocol):
    """The catalog. Read-only from the application's side: plans are
    configured through migrations and the admin path, never mutated as a
    side effect of serving a request, so no `create`/`update` appears
    here.
    """

    async def list_active(self, *, public_only: bool) -> list[Plan]:
        """Active plans in `sort_order`, then tier rank.

        `public_only` exists because the catalog legitimately holds rows
        the pricing page must not show — a grandfathered legacy plan
        still has to resolve for the workspaces on it, but publishing it
        would offer a price the product no longer sells.
        """
        ...

    async def get_by_slug(self, slug: PlanTier) -> Plan | None: ...


class WorkspaceUsageRepository(Protocol):
    """Standing resource counts for one workspace.

    Deliberately one call returning every dimension rather than a method
    per dimension: the entitlements endpoint needs all of them at once,
    and five round trips to render one panel is the N+1 this shape
    exists to prevent.

    The counts come from tables owned by other bounded contexts
    (`agents`, `teams`, `knowledge_bases`, MCP installations,
    `workspace_members`). Billing does **not** query them: each owning
    repository grew a `count_for_workspace` method, and the adapter
    behind this port composes those. Rule 5 forbids reaching into
    another context's tables, and a counting query is not an exception
    to it — a `WHERE deleted_at IS NULL` clause that the owning context
    later changes would silently start billing on a different definition
    of "an agent" than the product shows.
    """

    async def resource_usage(self, workspace_id: str) -> ResourceUsage: ...


class SubscriptionRepository(Protocol):
    """Subscriptions and their transition log.

    `record_transition` writes the new status *and* the event row in one
    call, on purpose: they are a single fact, and exposing "update the
    status" separately from "log that you updated it" would make the
    unlogged transition — the thing `billing-expert`'s checklist forbids
    — the easier of the two to write.
    """

    async def get_for_workspace(self, workspace_id: str) -> Subscription | None:
        """The workspace's live subscription, or `None` if it has never
        subscribed or its last subscription is canceled.

        Canceled subscriptions are excluded because "what is this
        workspace on right now" has exactly one answer, and a terminated
        row is not it — history is read through `list_events`.
        """
        ...

    async def get_by_id(self, subscription_id: str) -> Subscription | None: ...

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
    ) -> Subscription: ...

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
        # Field updates that accompany the transition — the new period
        # after a renewal, `past_due_since` on a first failure, and so
        # on. Passed with the transition rather than as a second write so
        # a crash cannot leave the status and its supporting dates
        # disagreeing.
        changes: dict[str, object],
    ) -> Subscription: ...

    async def set_cancel_at_period_end(
        self, *, subscription_id: str, cancel_at_period_end: bool
    ) -> Subscription: ...

    async def change_plan(
        self, *, subscription_id: str, plan_id: str, interval: BillingInterval
    ) -> Subscription: ...

    async def find_event_by_idempotency_key(self, key: str) -> str | None:
        """The subscription id a previously-recorded event belongs to.

        The replay check: a retried webhook or a re-run job asks first,
        and a hit means the transition already happened and must not
        happen again (`billing-expert` operating principle 5).
        """
        ...

    async def list_events(
        self, *, subscription_id: str, limit: int
    ) -> list[tuple[str, str, str, str, datetime]]:
        """`(trigger, from_status, to_status, actor, occurred_at)`, newest
        first — the billing history the UI renders.
        """
        ...


class UsageRepository(Protocol):
    """Durable metered usage. The billing source of truth (Rule 13).

    A Redis counter may drive a progress bar; the invoice reads these
    rows.
    """

    async def record(self, events: list[UsageEvent]) -> int:
        """Append events, skipping any whose idempotency key is already
        present. Returns how many were actually written.

        Takes a list rather than one event because the natural unit is a
        finished run — several dimensions at once — and a row-by-row loop
        is the bulk-write mistake `postgresql-expert` names explicitly.
        """
        ...

    async def usage_for_period(
        self, *, workspace_id: str, period_start: datetime, period_end: datetime
    ) -> PeriodUsage:
        """Live totals straight from the event partitions.

        The live-panel query. Distinct from `finalized_rollups`, which is
        what invoicing reads — mixing them would let an invoice change
        after issue because a late event arrived.
        """
        ...

    async def write_rollups(
        self,
        *,
        workspace_id: str,
        period_start: datetime,
        period_end: datetime,
        usage: PeriodUsage,
        finalize: bool,
    ) -> None:
        """Upsert the period's totals, keyed by
        `(workspace_id, period_start, dimension)` so a re-run recomputes
        rather than double-counts.
        """
        ...

    async def finalized_rollups(
        self, *, workspace_id: str, period_start: datetime
    ) -> PeriodUsage | None:
        """The frozen totals for a closed period, or `None` if the period
        has not been finalized. Invoicing refuses to proceed on `None`
        rather than billing a period still in progress.
        """
        ...


class CreditRepository(Protocol):
    """Credit balances and their ledger.

    `move` writes the balance and the ledger row together in one call,
    for the same reason `record_transition` does for subscriptions: they
    are one fact, and exposing them separately would make the unlogged
    balance change the easier of the two to write.
    """

    async def balance(self, workspace_id: str) -> int:
        """Zero for a workspace that has never held credit — the true
        balance, not a missing value.
        """
        ...

    async def move(
        self,
        *,
        workspace_id: str,
        reason: CreditReason,
        amount_cents: int,
        description: str,
        source_ref: str | None,
        expires_at: datetime | None,
        idempotency_key: str,
    ) -> int:
        """Apply one movement and return the new balance.

        Takes `SELECT ... FOR UPDATE` on the balance row: without it two
        concurrent spends each read the same balance and both approve,
        which is how a workspace spends credit it does not have.

        Idempotent by `idempotency_key` — a replayed grant returns the
        current balance rather than adding a second one.
        """
        ...

    async def history(self, *, workspace_id: str, limit: int) -> list[CreditTransaction]: ...

    async def ledger_sum(self, workspace_id: str) -> int:
        """The balance re-derived from the ledger. Used by reconciliation
        to prove the projection has not drifted.
        """
        ...


class CouponRepository(Protocol):
    async def get_by_code(self, code: str) -> Coupon | None: ...

    async def has_redeemed(self, *, coupon_id: str, workspace_id: str) -> bool: ...

    async def record_redemption(
        self,
        *,
        coupon_id: str,
        workspace_id: str,
        credited_cents: int,
        redeemed_by_user_id: str | None,
    ) -> None:
        """Write the redemption and bump the coupon's counter together.

        The unique `(coupon_id, workspace_id)` index is what makes a
        second attempt fail here rather than granting credit twice.
        """
        ...


class ReferralRepository(Protocol):
    async def create(
        self,
        *,
        referrer_workspace_id: str,
        referred_workspace_id: str,
        code: str,
    ) -> Referral: ...

    async def get_for_referred(self, referred_workspace_id: str) -> Referral | None: ...

    async def list_for_referrer(
        self, *, referrer_workspace_id: str, limit: int
    ) -> list[Referral]: ...

    async def transition(
        self,
        *,
        referral_id: str,
        status: ReferralStatus,
        referrer_reward_cents: int | None = None,
        referred_reward_cents: int | None = None,
        voided_reason: str | None = None,
    ) -> Referral: ...

    async def ensure_code_indexed(self, *, workspace_id: str, code: str) -> None:
        """Idempotent upsert into the reverse code->workspace index
        (Phase 11). A no-op if this workspace's code is already indexed —
        called every time a code is displayed, not just once, so the
        index self-heals if it was ever missed.
        """
        ...

    async def resolve_referrer(self, code: str) -> str | None:
        """The `workspace_id` a shareable code belongs to, or `None` for
        an unknown/never-indexed code. Never raises on a bad code — a
        stranger can paste anything into a signup flow.
        """
        ...


class WebhookEventRepository(Protocol):
    """The provider-event delivery log.

    `claim` and `resolve` are separate calls because the work between
    them is the state change the event causes: claiming first, in the
    same transaction, is what makes a concurrent redelivery lose the race
    at the database rather than duplicate the effect.
    """

    async def claim(
        self,
        *,
        provider: str,
        provider_event_id: str,
        event_type: str,
        workspace_id: str | None,
    ) -> bool:
        """Record this event as received. `False` if it was already
        recorded — meaning some other delivery of the same event owns it
        and this one must do nothing.
        """
        ...

    async def resolve(
        self,
        *,
        provider: str,
        provider_event_id: str,
        status: str,
        error: str | None,
    ) -> None: ...

    async def was_processed(self, *, provider: str, provider_event_id: str) -> bool: ...


class CustomerRepository(Protocol):
    async def get_for_workspace(self, workspace_id: str) -> BillingCustomer | None: ...

    async def upsert(
        self,
        *,
        workspace_id: str,
        provider: PaymentProvider,
        provider_customer_id: str,
        billing_email: str | None,
    ) -> BillingCustomer:
        """Idempotent by `workspace_id`.

        Upsert rather than create because the caller is usually reacting
        to a processor event that may be redelivered, and a second
        delivery must not create a second customer record for the same
        workspace — two processor identities for one tenant is how
        invoices start landing on the wrong account.
        """
        ...
