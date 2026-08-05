"""`/api/v1/workspaces/{workspace_id}/billing/entitlements` — what this
workspace's plan allows, against what it is currently using.

`require_viewer`: every member needs to see why a create button is
disabled, and knowing the workspace's own quota is not privileged
information. Changing the plan is a separate, admin-gated action.

`workspace_id` is resolved from the authenticated identity by the
dependency chain, never read from the path directly (Rule 6, Rule 11).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import require_viewer
from agentverse_api.billing_service.application.entitlement_service import EntitlementService
from agentverse_api.billing_service.interface.dependencies.services import (
    get_entitlement_service,
)
from agentverse_api.billing_service.interface.schemas.entitlements import (
    EntitlementsResponse,
    to_entitlements_response,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["billing-entitlements"])


@router.get("/{workspace_id}/billing/entitlements", response_model=EntitlementsResponse)
async def get_entitlements_route(
    context: WorkspaceContext = Depends(require_viewer),
    service: EntitlementService = Depends(get_entitlement_service),
) -> EntitlementsResponse:
    entitlements = await service.entitlements_for(context.workspace_id)
    return to_entitlements_response(entitlements)
