"""Response schemas for metered usage and the invoice preview."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from agentverse_api.billing_service.domain.invoice import DraftInvoice
from agentverse_api.billing_service.domain.usage import LEVEL_DIMENSIONS, PeriodUsage


class DimensionUsageResponse(BaseModel):
    dimension: str
    quantity: int
    #: `true` for storage: a workspace holding 5 GB all month used 5 GB,
    #: not 150 GB-days. The client renders these as a current level
    #: rather than an accumulating counter.
    is_level: bool


class PeriodUsageResponse(BaseModel):
    """Live usage for the current billing period.

    Carries its period boundaries because "usage this month" and "usage
    this billing period" are different questions for every customer whose
    subscription did not start on the 1st — and the panel has to show
    which one it is answering.
    """

    workspace_id: str
    period_start: datetime
    period_end: datetime
    dimensions: list[DimensionUsageResponse]


class InvoiceLineResponse(BaseModel):
    kind: str
    dimension: str | None
    description: str
    quantity: int
    unit_label: str
    amount_cents: int


class DraftInvoiceResponse(BaseModel):
    """The flat fee and each overage as separate lines, never one total.

    A customer disputing a charge needs to see which dimension drove it;
    a single number cannot be decomposed back into "Pro plan" plus
    "4,000 agent runs over allowance".
    """

    workspace_id: str
    period_start: datetime
    period_end: datetime
    currency: str
    lines: list[InvoiceLineResponse]
    subtotal_cents: int
    has_overage: bool


def to_period_usage_response(usage: PeriodUsage) -> PeriodUsageResponse:
    return PeriodUsageResponse(
        workspace_id=usage.workspace_id,
        period_start=usage.period_start,
        period_end=usage.period_end,
        dimensions=[
            DimensionUsageResponse(
                dimension=dimension.value,
                quantity=row.quantity,
                is_level=dimension in LEVEL_DIMENSIONS,
            )
            for dimension, row in sorted(usage.dimensions.items(), key=lambda item: item[0].value)
        ],
    )


def to_draft_invoice_response(invoice: DraftInvoice) -> DraftInvoiceResponse:
    return DraftInvoiceResponse(
        workspace_id=invoice.workspace_id,
        period_start=invoice.period_start,
        period_end=invoice.period_end,
        currency=invoice.currency,
        lines=[
            InvoiceLineResponse(
                kind=line.kind,
                dimension=line.dimension.value if line.dimension else None,
                description=line.description,
                quantity=line.quantity,
                unit_label=line.unit_label,
                amount_cents=line.amount_cents,
            )
            for line in invoice.lines
        ],
        subtotal_cents=invoice.subtotal_cents,
        has_overage=invoice.has_overage,
    )
