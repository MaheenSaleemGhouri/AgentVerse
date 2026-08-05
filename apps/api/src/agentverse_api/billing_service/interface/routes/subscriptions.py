"""`/api/v1/workspaces/{workspace_id}/billing/subscription` — read-only.

**Why there are no mutating routes here yet.** Starting, changing,
pausing or canceling a subscription all have to move money and stay in
step with the payment processor. An endpoint that changed only this
platform's rows would leave the processor still charging a canceled
customer, or stop charging one this side still serves — and the
divergence would be invisible until an invoice arrived. Those routes
land in M3, driven through the provider port, so the local transition and
the processor call are one operation.

The service underneath is complete: every transition, proration and
dunning decision is implemented and tested here. What M3 adds is the
counterpart at the processor, not the logic.

`require_viewer` on both routes: a member seeing which plan their
workspace is on, and why a limit applies, is not privileged. Nothing here
exposes a payment method, an amount charged, or a processor identifier.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import require_viewer
from agentverse_api.billing_service.application.subscription_service import SubscriptionService
from agentverse_api.billing_service.domain.exceptions import SubscriptionNotFoundError
from agentverse_api.billing_service.interface.dependencies.services import (
    get_subscription_service,
)
from agentverse_api.billing_service.interface.schemas.subscription import (
    SubscriptionEventResponse,
    SubscriptionHistoryResponse,
    SubscriptionResponse,
    to_subscription_response,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["billing-subscription"])


@router.get("/{workspace_id}/billing/subscription", response_model=SubscriptionResponse)
async def get_subscription_route(
    context: WorkspaceContext = Depends(require_viewer),
    service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionResponse:
    """404 when the workspace has never subscribed.

    A Free workspace is operating exactly as intended, so this is not an
    error *about the workspace* — but the caller asked for a
    subscription, and there is none. Clients read Free from the
    entitlements endpoint, which always answers.
    """
    try:
        subscription = await service.require_current(context.workspace_id)
    except SubscriptionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This workspace has no subscription; it is on the Free plan.",
        ) from exc
    return to_subscription_response(subscription, now=service.now())


@router.get(
    "/{workspace_id}/billing/subscription/events",
    response_model=SubscriptionHistoryResponse,
)
async def list_subscription_events_route(
    context: WorkspaceContext = Depends(require_viewer),
    service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionHistoryResponse:
    """The transition log, newest first.

    Returns an empty list rather than 404 for a workspace with no
    subscription: "this workspace has no billing history" is a true,
    renderable answer, and the timeline component should show an empty
    state rather than an error.
    """
    events = await service.history(workspace_id=context.workspace_id)
    return SubscriptionHistoryResponse(
        data=[
            SubscriptionEventResponse(
                trigger=trigger,
                from_status=from_status,
                to_status=to_status,
                actor=actor,
                occurred_at=occurred_at,
            )
            for trigger, from_status, to_status, actor, occurred_at in events
        ]
    )
