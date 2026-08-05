"""Repository ports for the billing context.

`infrastructure/repositories.py` implements these against Postgres;
`tests/` implements them in memory. Application-layer use cases depend
only on what is declared here (CLAUDE.md §5).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from agentverse_api.billing_service.domain.customer import BillingCustomer, PaymentProvider
from agentverse_api.billing_service.domain.entitlements import ResourceUsage
from agentverse_api.billing_service.domain.plan import BillingInterval, Plan, PlanTier
from agentverse_api.billing_service.domain.subscription import (
    Subscription,
    SubscriptionStatus,
    SubscriptionTrigger,
)


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
