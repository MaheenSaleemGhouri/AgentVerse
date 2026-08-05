"""`/api/v1/workspaces/{workspace_id}/billing/usage` and the invoice
preview.

`require_viewer` on both: a member needs to see why a run was refused,
and a workspace's own consumption against its own quota is not
privileged information. Neither route exposes an amount charged, a
payment method, or a provider identifier — those live on the
admin-gated surface in `billing_actions.py`.

The preview is explicitly a forecast of the period in progress.
`saas-strategist`'s no-surprise-billing rule in practice: the overage a
customer will owe is visible before the invoice, not discovered on it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import require_viewer
from agentverse_api.billing_service.application.invoicing_service import InvoicingService
from agentverse_api.billing_service.application.usage_service import UsageService
from agentverse_api.billing_service.interface.dependencies.services import (
    get_invoicing_service,
    get_usage_service,
)
from agentverse_api.billing_service.interface.schemas.usage import (
    DraftInvoiceResponse,
    PeriodUsageResponse,
    to_draft_invoice_response,
    to_period_usage_response,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["billing-usage"])


@router.get("/{workspace_id}/billing/usage", response_model=PeriodUsageResponse)
async def get_usage_route(
    context: WorkspaceContext = Depends(require_viewer),
    service: UsageService = Depends(get_usage_service),
) -> PeriodUsageResponse:
    """Live usage for the current billing period.

    Read from the durable event rows, not a cached counter (Rule 13). A
    dimension with no events reports zero, which is the true count rather
    than a missing value — every dimension always has an answer.
    """
    usage = await service.current_period_usage(context.workspace_id)
    return to_period_usage_response(usage)


@router.get("/{workspace_id}/billing/invoice-preview", response_model=DraftInvoiceResponse)
async def preview_invoice_route(
    context: WorkspaceContext = Depends(require_viewer),
    service: InvoicingService = Depends(get_invoicing_service),
) -> DraftInvoiceResponse:
    """What this period would cost if it closed right now.

    A forecast, deliberately built from live usage — which is correct
    here and would be a mistake for an issued invoice, where the totals
    must be frozen first so the number cannot move between being shown
    and being paid.
    """
    invoice = await service.preview_current_period(context.workspace_id)
    return to_draft_invoice_response(invoice)
