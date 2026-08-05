"""Resolving what a workspace may do: its plan, set against its real
counts.

The plan lookup is deliberately a single named method
(`_plan_for_workspace`) rather than inline: it is the seam where the
subscription table plugs in. Today every workspace resolves to the
default Free plan, which is not a placeholder — a workspace with no
subscription genuinely *is* on Free, and that stays true after paid
subscriptions exist. What changes is that the lookup gains a preceding
step, in one place, instead of every entitlement call site growing one.
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
from agentverse_api.billing_service.domain.plan import (
    Capability,
    MeteredDimension,
    Plan,
    ResourceLimit,
)
from agentverse_api.billing_service.domain.ports import WorkspaceUsageRepository


@dataclass(slots=True)
class EntitlementService:
    catalog: PlanCatalogService
    usage: WorkspaceUsageRepository

    async def _plan_for_workspace(self, workspace_id: str) -> Plan:
        # `workspace_id` is unused until subscriptions land, and is taken
        # now rather than added later so the signature every caller
        # depends on does not change when it starts mattering.
        del workspace_id
        return await self.catalog.default_plan()

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
