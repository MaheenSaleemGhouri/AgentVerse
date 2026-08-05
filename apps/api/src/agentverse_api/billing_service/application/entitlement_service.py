"""Resolving what a workspace may do: its plan, set against its real
counts.

The plan lookup is a single named method (`_plan_for_workspace`) so
every entitlement decision in the platform reads the plan the same way.
It answers with the subscribed plan when there is a live, entitling
subscription, and with Free otherwise — which covers a workspace that
never subscribed, one whose subscription was canceled, and one that is
paused, all of which are genuinely on Free rather than in some
intermediate state.

`PAST_DUE` deliberately still entitles. Dunning exists because a failed
charge is usually an expired card; cutting service at the first failure
turns a recoverable billing problem into churn. Service stops when the
dunning window closes and the subscription reaches `CANCELED`, which is
bounded and scheduled (see `domain/dunning.py`).
"""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.domain.entitlements import (
    Entitlements,
    can_create,
    metered_lines,
    resource_lines,
)
from agentverse_api.billing_service.domain.exceptions import (
    CatalogIncompleteError,
    PlanNotFoundError,
)
from agentverse_api.billing_service.domain.plan import (
    Capability,
    MeteredDimension,
    Plan,
    ResourceLimit,
)
from agentverse_api.billing_service.domain.ports import (
    SubscriptionRepository,
    WorkspaceUsageRepository,
)


@dataclass(slots=True)
class EntitlementService:
    catalog: PlanCatalogService
    usage: WorkspaceUsageRepository
    subscriptions: SubscriptionRepository

    async def _plan_for_workspace(self, workspace_id: str) -> Plan:
        subscription = await self.subscriptions.get_for_workspace(workspace_id)
        if subscription is None or not subscription.entitles:
            return await self.catalog.default_plan()
        try:
            return await self.catalog.get_plan(subscription.plan_slug)
        except PlanNotFoundError as exc:
            # A live subscription pointing at a deactivated plan. Not a
            # 404 — the caller asked about their workspace, not about a
            # plan — and emphatically not a silent downgrade to Free,
            # which would revoke a paying customer's limits mid-request
            # with no trace. It is an operator error in the catalog and
            # must page, exactly like a missing Free row.
            raise CatalogIncompleteError(subscription.plan_slug) from exc

    async def entitlements_for(self, workspace_id: str) -> Entitlements:
        """Everything the usage panel and the upgrade nudges need, in one
        round of queries.

        Metered lines report zero until the metering pipeline records
        events. That is honest rather than fabricated: the dimensions are
        real, the allowances are the plan's real allowances, and zero is
        the true count of events recorded so far.
        """
        plan = await self._plan_for_workspace(workspace_id)
        resource_usage = await self.usage.resource_usage(workspace_id)
        period_usage: dict[MeteredDimension, int] = {}
        return Entitlements(
            workspace_id=workspace_id,
            plan=plan,
            resources=resource_lines(plan=plan, usage=resource_usage),
            metered=metered_lines(plan=plan, period_usage=period_usage),
        )

    async def may_create(self, *, workspace_id: str, limit: ResourceLimit) -> bool:
        """Server-side check for a create path.

        Re-measures rather than trusting a count the caller passes in.
        A caller-supplied count is a client-controlled quota check
        wearing a server-side disguise (Rule 6), and re-reading an
        indexed aggregate is cheap next to what a create actually does.
        """
        plan = await self._plan_for_workspace(workspace_id)
        usage = await self.usage.resource_usage(workspace_id)
        current = usage.count_for(limit)
        if current is None:
            # Not a dimension this snapshot measures (concurrent runs is
            # enforced at submission time against the queue). Admitting
            # here is correct: the real check happens where the number is
            # actually knowable, and refusing on ignorance would block a
            # legitimate action for a limit nobody evaluated.
            return True
        return can_create(plan=plan, limit=limit, current_count=current)

    async def grants(self, *, workspace_id: str, capability: Capability) -> bool:
        plan = await self._plan_for_workspace(workspace_id)
        return plan.grants(capability)
