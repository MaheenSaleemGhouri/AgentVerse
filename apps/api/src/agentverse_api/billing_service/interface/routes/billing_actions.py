"""The money-moving billing surface, under
`/api/v1/workspaces/{workspace_id}/billing/`.

**Everything here is `require_admin`, not `require_viewer`.** M2's read
routes are viewer-gated because knowing which plan a workspace is on
explains why a limit applies. These are different: they expose invoice
amounts and card metadata, or they change what the workspace is charged.
A member who can see the quota should not be able to read the company's
invoice history or cancel its subscription.

`workspace_id` comes from the authenticated context in every handler,
never from the path parameter directly (Rule 6, Rule 11). The path
segment exists for routing and readability; the dependency chain is what
decides which tenant's data is touched.

Errors map to a fixed set: 402/409 for state the caller could resolve,
502 for a provider failure, 503 when this environment has no provider
configured at all. None of them leaks a provider exception message
verbatim.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import require_admin
from agentverse_api.billing_service.application.billing_actions_service import (
    BillingActionsService,
)
from agentverse_api.billing_service.domain.exceptions import (
    PlanNotPurchasableError,
    SubscriptionAlreadyExistsError,
    SubscriptionNotFoundError,
)
from agentverse_api.billing_service.domain.payment_provider import ProviderError
from agentverse_api.billing_service.domain.subscription import InvalidTransitionError
from agentverse_api.billing_service.interface.dependencies.services import (
    get_billing_actions_service,
)
from agentverse_api.billing_service.interface.schemas.billing_actions import (
    CancelRequest,
    CheckoutRequest,
    CheckoutResponse,
    InvoiceListResponse,
    PaymentMethodListResponse,
    PlanChangeQuoteResponse,
    PlanChangeRequest,
    PortalResponse,
    RefundRequest,
    RefundResponse,
    to_invoice_response,
    to_payment_method_response,
    to_quote_response,
)
from agentverse_api.billing_service.interface.schemas.subscription import (
    SubscriptionResponse,
    to_subscription_response,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["billing-actions"])


@router.post(
    "/{workspace_id}/billing/checkout-session",
    response_model=CheckoutResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_checkout_route(
    body: CheckoutRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: BillingActionsService = Depends(get_billing_actions_service),
) -> CheckoutResponse:
    """Start a hosted checkout.

    No subscription row is created here — it is created when the provider
    confirms payment via webhook. Creating one optimistically would leave
    a phantom subscription for every customer who opened the page and
    closed the tab.
    """
    try:
        session = await service.start_checkout(
            workspace_id=context.workspace_id,
            plan_slug=body.plan_slug,
            interval=body.interval,
            success_url=f"/dashboard/{context.workspace_id}/billing?checkout=success",
            cancel_url=f"/dashboard/{context.workspace_id}/billing?checkout=cancelled",
            billing_email=None,
            workspace_name=None,
            coupon_code=body.coupon_code,
        )
    except SubscriptionAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This workspace already has a subscription; change the plan instead.",
        ) from exc
    except PlanNotPurchasableError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.detail
        ) from exc
    return CheckoutResponse(checkout_url=session.url, session_id=session.session_id)


@router.post("/{workspace_id}/billing/portal-session", response_model=PortalResponse)
async def create_portal_route(
    context: WorkspaceContext = Depends(require_admin),
    service: BillingActionsService = Depends(get_billing_actions_service),
) -> PortalResponse:
    """The provider's own management surface — payment methods, plan
    changes, cancellation, invoice history.

    Preferred over rebuilding each of those here: it is where the card
    form lives, and every card field this product does not build is PCI
    scope it does not carry.
    """
    try:
        session = await service.open_portal(
            workspace_id=context.workspace_id,
            return_url=f"/dashboard/{context.workspace_id}/billing",
        )
    except SubscriptionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This workspace has no billing account yet; start a checkout first.",
        ) from exc
    return PortalResponse(portal_url=session.url)


@router.post("/{workspace_id}/billing/subscription/cancel", response_model=SubscriptionResponse)
async def cancel_subscription_route(
    body: CancelRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: BillingActionsService = Depends(get_billing_actions_service),
) -> SubscriptionResponse:
    try:
        subscription = await service.cancel(
            workspace_id=context.workspace_id,
            actor=context.user_id,
            at_period_end=body.at_period_end,
            reason=body.reason,
        )
    except SubscriptionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This workspace has no subscription to cancel.",
        ) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return to_subscription_response(subscription, now=service.subscriptions.now())


@router.post("/{workspace_id}/billing/subscription/resume", response_model=SubscriptionResponse)
async def resume_subscription_route(
    context: WorkspaceContext = Depends(require_admin),
    service: BillingActionsService = Depends(get_billing_actions_service),
) -> SubscriptionResponse:
    """Undo a scheduled cancellation while the paid period is still open."""
    try:
        subscription = await service.resume(workspace_id=context.workspace_id)
    except SubscriptionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This workspace has no subscription to resume.",
        ) from exc
    return to_subscription_response(subscription, now=service.subscriptions.now())


@router.post("/{workspace_id}/billing/subscription/pause", response_model=SubscriptionResponse)
async def pause_subscription_route(
    context: WorkspaceContext = Depends(require_admin),
    service: BillingActionsService = Depends(get_billing_actions_service),
) -> SubscriptionResponse:
    try:
        subscription = await service.pause(workspace_id=context.workspace_id, actor=context.user_id)
    except SubscriptionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This workspace has no subscription to pause.",
        ) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return to_subscription_response(subscription, now=service.subscriptions.now())


@router.post("/{workspace_id}/billing/subscription/unpause", response_model=SubscriptionResponse)
async def unpause_subscription_route(
    context: WorkspaceContext = Depends(require_admin),
    service: BillingActionsService = Depends(get_billing_actions_service),
) -> SubscriptionResponse:
    try:
        subscription = await service.unpause(
            workspace_id=context.workspace_id, actor=context.user_id
        )
    except SubscriptionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This workspace has no subscription to resume.",
        ) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return to_subscription_response(subscription, now=service.subscriptions.now())


@router.post("/{workspace_id}/billing/subscription/quote", response_model=PlanChangeQuoteResponse)
async def quote_plan_change_route(
    body: PlanChangeRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: BillingActionsService = Depends(get_billing_actions_service),
) -> PlanChangeQuoteResponse:
    """What a plan change costs, without making it.

    Shown before the confirm button: a customer should never first learn
    a proration figure from their statement.
    """
    try:
        quote = await service.quote_plan_change(
            workspace_id=context.workspace_id,
            target_slug=body.plan_slug,
            interval=body.interval,
        )
    except SubscriptionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This workspace has no subscription to change.",
        ) from exc
    except PlanNotPurchasableError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.detail
        ) from exc
    return to_quote_response(quote)


@router.post(
    "/{workspace_id}/billing/subscription/change-plan", response_model=SubscriptionResponse
)
async def change_plan_route(
    body: PlanChangeRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: BillingActionsService = Depends(get_billing_actions_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> SubscriptionResponse:
    """Change plan mid-cycle.

    `Idempotency-Key` is required (CLAUDE.md §7: billing-affecting
    endpoints enforce it). Without one, a retried request after a
    timeout would apply a second plan change — and each one becomes an
    invoice line.
    """
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An Idempotency-Key header is required for billing-affecting requests.",
        )
    try:
        subscription, _ = await service.change_plan(
            workspace_id=context.workspace_id,
            target_slug=body.plan_slug,
            interval=body.interval,
            actor=context.user_id,
            idempotency_key=idempotency_key,
        )
    except SubscriptionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This workspace has no subscription to change.",
        ) from exc
    except PlanNotPurchasableError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.detail
        ) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return to_subscription_response(subscription, now=service.subscriptions.now())


@router.get("/{workspace_id}/billing/invoices", response_model=InvoiceListResponse)
async def list_invoices_route(
    context: WorkspaceContext = Depends(require_admin),
    service: BillingActionsService = Depends(get_billing_actions_service),
    limit: int = 24,
) -> InvoiceListResponse:
    """Read straight from the provider, never a local mirror.

    Invoice PDFs are the provider's to hold; a cached copy here would be
    one more thing that can be stale and one more place financial
    documents live.
    """
    invoices = await service.list_invoices(
        workspace_id=context.workspace_id, limit=min(max(limit, 1), 100)
    )
    return InvoiceListResponse(data=[to_invoice_response(invoice) for invoice in invoices])


@router.get("/{workspace_id}/billing/payment-methods", response_model=PaymentMethodListResponse)
async def list_payment_methods_route(
    context: WorkspaceContext = Depends(require_admin),
    service: BillingActionsService = Depends(get_billing_actions_service),
) -> PaymentMethodListResponse:
    """Brand, last four and expiry only — read per request, never stored.

    Adding or removing a card happens on the provider's hosted portal, so
    no card field exists anywhere in this codebase.
    """
    methods = await service.list_payment_methods(workspace_id=context.workspace_id)
    return PaymentMethodListResponse(
        data=[to_payment_method_response(method) for method in methods]
    )


@router.post(
    "/{workspace_id}/billing/refunds",
    response_model=RefundResponse,
    status_code=status.HTTP_201_CREATED,
)
async def refund_route(
    body: RefundRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: BillingActionsService = Depends(get_billing_actions_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RefundResponse:
    """Refund an invoice, fully or partially.

    Never automatic: a downgrade produces a credit against the next
    invoice, and money actually leaving the company is a separate,
    deliberately authorized action. The invoice is checked to belong to
    this workspace's customer before anything is refunded — an invoice id
    from another tenant must not refund their charge (Rule 11).
    """
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An Idempotency-Key header is required for billing-affecting requests.",
        )
    try:
        refund_id = await service.refund(
            workspace_id=context.workspace_id,
            invoice_id=body.invoice_id,
            amount_cents=body.amount_cents,
            reason=body.reason,
        )
    except SubscriptionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This workspace has no billing account.",
        ) from exc
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.detail
        ) from exc
    return RefundResponse(refund_id=refund_id)
