"""Comparing this system's subscription projection against the provider's
actual state.

Webhooks are the primary path and they are reliable, but they are not
perfect: a delivery can be dropped while this service is down longer than
the provider's retry window, an event can be processed and rolled back by
a crash, and a change made in the provider's dashboard by a human may
emit nothing this system subscribes to. Every one of those leaves silent
drift — a customer being charged for a plan they are not being served, or
served a plan they are not being charged for — and neither shows up in
any error log.

So this exists as a scheduled comparison. It **reports, it does not
repair.** Automatically rewriting subscription state from a comparison
would mean a bug here could cancel paying customers in bulk, and the
findings are rare enough that a human deciding each one is affordable.
That tradeoff is the whole design.

`postgresql-expert` owns the query shape; this module owns what counts as
a discrepancy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from agentverse_api.billing_service.domain.payment_provider import (
    PaymentProviderPort,
    ProviderError,
)
from agentverse_api.billing_service.domain.ports import SubscriptionRepository
from agentverse_api.billing_service.domain.subscription import (
    Subscription,
    SubscriptionStatus,
)

logger = logging.getLogger(__name__)

#: Provider statuses that mean "this subscription is live and paying",
#: mapped onto the statuses this system considers entitling. Anything
#: outside this mapping is a genuine mismatch rather than a vocabulary
#: difference.
_PROVIDER_LIVE_STATUSES: frozenset[str] = frozenset({"active", "trialing", "past_due"})


class DiscrepancyKind(StrEnum):
    MISSING_AT_PROVIDER = "missing_at_provider"
    STATUS_MISMATCH = "status_mismatch"
    CANCELLATION_MISMATCH = "cancellation_mismatch"
    PERIOD_DRIFT = "period_drift"
    UNLINKED = "unlinked"


@dataclass(frozen=True, slots=True)
class Discrepancy:
    workspace_id: str
    subscription_id: str
    kind: DiscrepancyKind
    detail: str
    #: What each side believes, verbatim, so the finding can be acted on
    #: without re-running the comparison.
    local: str
    remote: str


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    checked: int
    discrepancies: list[Discrepancy]
    ran_at: datetime

    @property
    def is_clean(self) -> bool:
        return not self.discrepancies


@dataclass(slots=True)
class ReconciliationService:
    provider: PaymentProviderPort
    subscriptions: SubscriptionRepository

    async def reconcile_workspace(self, workspace_id: str) -> list[Discrepancy]:
        subscription = await self.subscriptions.get_for_workspace(workspace_id)
        if subscription is None:
            # Nothing local to disagree with. A provider-side
            # subscription for a workspace with no local row would be
            # found by the opposite sweep (provider list -> local), which
            # needs a provider-side listing endpoint this port does not
            # expose; noted rather than silently implied.
            return []
        return await self._compare(subscription)

    async def _compare(self, subscription: Subscription) -> list[Discrepancy]:
        if subscription.provider_subscription_id is None:
            # A live subscription with no provider link is not
            # necessarily wrong — a plan granted by an operator, or a
            # Free-tier row — but nothing is charging for it, which is
            # worth surfacing rather than assuming.
            if subscription.plan_slug.value == "free":
                return []
            return [
                Discrepancy(
                    workspace_id=subscription.workspace_id,
                    subscription_id=subscription.id,
                    kind=DiscrepancyKind.UNLINKED,
                    detail=(
                        "A paid subscription with no payment-provider link: "
                        "nothing is charging for it."
                    ),
                    local=subscription.plan_slug.value,
                    remote="(none)",
                )
            ]

        try:
            remote = await self.provider.get_subscription_state(
                provider_subscription_id=subscription.provider_subscription_id
            )
        except ProviderError:
            # A provider outage is not a discrepancy. Reporting one would
            # fill the report with noise on exactly the day it matters
            # least.
            logger.warning(
                "reconciliation_provider_unavailable",
                extra={"workspace_id": subscription.workspace_id},
            )
            return []

        if remote is None:
            return [
                Discrepancy(
                    workspace_id=subscription.workspace_id,
                    subscription_id=subscription.id,
                    kind=DiscrepancyKind.MISSING_AT_PROVIDER,
                    detail=(
                        "This system holds a live subscription the provider has never "
                        "heard of; the workspace is being served and not billed."
                    ),
                    local=subscription.status.value,
                    remote="(not found)",
                )
            ]

        found: list[Discrepancy] = []
        local_live = subscription.status in (
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.TRIALING,
            SubscriptionStatus.PAST_DUE,
        )
        remote_live = remote.status in _PROVIDER_LIVE_STATUSES
        if local_live != remote_live:
            found.append(
                Discrepancy(
                    workspace_id=subscription.workspace_id,
                    subscription_id=subscription.id,
                    kind=DiscrepancyKind.STATUS_MISMATCH,
                    detail=(
                        "One side considers this subscription live and the other does "
                        "not — the workspace is either served unpaid or paying unserved."
                    ),
                    local=subscription.status.value,
                    remote=remote.status,
                )
            )
        if subscription.cancel_at_period_end != remote.cancel_at_period_end:
            found.append(
                Discrepancy(
                    workspace_id=subscription.workspace_id,
                    subscription_id=subscription.id,
                    kind=DiscrepancyKind.CANCELLATION_MISMATCH,
                    detail=(
                        "A scheduled cancellation is recorded on one side only; the "
                        "subscription will end on one and renew on the other."
                    ),
                    local=str(subscription.cancel_at_period_end),
                    remote=str(remote.cancel_at_period_end),
                )
            )
        if remote.current_period_end is not None:
            drift = abs((remote.current_period_end - subscription.current_period_end).days)
            # A day of tolerance: the two clocks advance a period at
            # slightly different moments, and flagging that would report
            # every renewal as a finding.
            if drift > 1:
                found.append(
                    Discrepancy(
                        workspace_id=subscription.workspace_id,
                        subscription_id=subscription.id,
                        kind=DiscrepancyKind.PERIOD_DRIFT,
                        detail=(
                            f"Billing periods disagree by {drift} days; usage would be "
                            "aggregated into the wrong invoice."
                        ),
                        local=subscription.current_period_end.isoformat(),
                        remote=remote.current_period_end.isoformat(),
                    )
                )
        return found
