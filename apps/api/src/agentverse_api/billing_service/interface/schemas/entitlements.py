"""Response schema for a workspace's entitlements."""

from __future__ import annotations

from pydantic import BaseModel

from agentverse_api.billing_service.domain.entitlements import EntitlementLine, Entitlements
from agentverse_api.billing_service.interface.schemas.plan import PlanResponse, to_plan_response


class EntitlementLineResponse(BaseModel):
    """One dimension's headroom.

    `limit`, `remaining` and `percent_used` are all `null` together when
    the dimension is unlimited. The client must branch on `limit is null`
    and render "Unlimited" — a progress bar with a null maximum has
    nothing truthful to draw.
    """

    dimension: str
    limit: int | None
    used: int
    remaining: int | None
    percent_used: int | None
    at_limit: bool
    approaching_limit: bool


class EntitlementsResponse(BaseModel):
    workspace_id: str
    plan: PlanResponse
    #: Standing counts — how many exist right now.
    resources: list[EntitlementLineResponse]
    #: Period counts — how much has accrued this billing period.
    metered: list[EntitlementLineResponse]
    capabilities: list[str]


def _to_line(line: EntitlementLine) -> EntitlementLineResponse:
    return EntitlementLineResponse(
        dimension=line.dimension,
        limit=line.limit,
        used=line.used,
        remaining=line.remaining,
        percent_used=line.percent_used,
        at_limit=line.at_limit,
        approaching_limit=line.approaching_limit,
    )


def to_entitlements_response(entitlements: Entitlements) -> EntitlementsResponse:
    return EntitlementsResponse(
        workspace_id=entitlements.workspace_id,
        plan=to_plan_response(entitlements.plan),
        resources=[_to_line(line) for line in entitlements.resources],
        metered=[_to_line(line) for line in entitlements.metered],
        capabilities=sorted(capability.value for capability in entitlements.capabilities),
    )
