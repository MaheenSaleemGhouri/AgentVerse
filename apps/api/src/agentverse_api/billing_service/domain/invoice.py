"""Turning a period's usage into invoice lines.

Pure integer arithmetic in cents. This module is the **only** place
micro-USD becomes cents, and it does so exactly once per invoice, at the
boundary `agentverse_shared.cost_accounting` was designed for.

Three rules shape everything below.

**The flat fee and each overage are separate lines.** Never one opaque
total. `saas-strategist`'s standard, and the practical reason is that a
customer disputing a charge needs to see which dimension drove it —
a single number cannot be decomposed back into "Pro plan" plus "4,000
agent runs over allowance".

**Every line traces to a source.** A line is either the plan's published
price for the interval, or an overage computed from a specific
dimension's allowance, recorded quantity and per-increment rate. There is
no line whose amount cannot be recomputed from stored values, which is
what makes an invoice defensible months later.

**A dimension with no overage rate is never billed.** Exceeding it was
refused at the API boundary, not charged. That is what makes Free
genuinely free: a free workspace hits its limit and is stopped, and there
is no code path that can produce an invoice line for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from agentverse_shared.cost_accounting import micro_usd_to_cents

from agentverse_api.billing_service.domain.plan import (
    BillingInterval,
    MeteredDimension,
    Plan,
    overage_cents,
    overage_units,
    price_cents,
)
from agentverse_api.billing_service.domain.usage import PeriodUsage


@dataclass(frozen=True, slots=True)
class InvoiceLine:
    """One billable line, in integer cents.

    `quantity` and `unit_label` exist so the line renders as
    "4,000 agent runs over 10,000 included" rather than as a bare
    amount. The customer-facing description is assembled by the UI from
    these fields rather than stored as a string, so a wording change is
    not a data migration.
    """

    kind: str
    dimension: MeteredDimension | None
    description: str
    quantity: int
    unit_label: str
    amount_cents: int


@dataclass(frozen=True, slots=True)
class DraftInvoice:
    """What a workspace owes for one period, before the provider issues
    the real invoice.

    "Draft" is literal: this system computes it to *show* the customer
    and to check the provider's number against, not to charge. The
    payment provider issues and collects. Two independent computations
    that agree is the reconciliation; one computation nobody can check is
    not.
    """

    workspace_id: str
    period_start: datetime
    period_end: datetime
    currency: str
    lines: list[InvoiceLine]
    #: What the platform paid providers this period. Never charged —
    #: margin input only, and kept on the draft so the two numbers can be
    #: compared without re-querying.
    platform_cost_cents: int

    @property
    def subtotal_cents(self) -> int:
        return sum(line.amount_cents for line in self.lines)

    @property
    def has_overage(self) -> bool:
        return any(line.kind == "overage" for line in self.lines)


def _overage_line(*, plan: Plan, dimension: MeteredDimension, used: int) -> InvoiceLine | None:
    """One dimension's overage, or `None` if it is not billable.

    Returns `None` in three cases that look different but are all "no
    charge": the plan has no overage rate for this dimension (exceeding
    it was refused, not billed), the allowance is unlimited, or usage is
    within the allowance.
    """
    rate = plan.overage_rates.get(dimension)
    if rate is None:
        return None
    allowance = plan.metered_allowance(dimension)
    if allowance is None:
        return None
    units = overage_units(allowance=allowance, used=used, increment=rate.billing_increment)
    if units == 0:
        return None
    amount = overage_cents(allowance=allowance, used=used, rate=rate)
    excess = used - allowance
    return InvoiceLine(
        kind="overage",
        dimension=dimension,
        description=(
            f"{dimension.value.replace('_', ' ')} over the included "
            f"{allowance:,} ({excess:,} extra, billed as {units:,} × "
            f"{rate.billing_increment:,})"
        ),
        quantity=excess,
        unit_label=dimension.value,
        amount_cents=amount,
    )


def build_draft_invoice(
    *, plan: Plan, interval: BillingInterval, usage: PeriodUsage
) -> DraftInvoice:
    """Assemble the period's lines.

    The flat fee comes first because that is the order a customer reads
    an invoice in, then overages in the enum's declaration order — stable
    rather than dictionary-insertion order, so two invoices for the same
    workspace list their lines the same way and can be compared by eye.

    A custom-priced plan contributes no flat-fee line: Enterprise is
    quoted and invoiced by sales, and inventing a zero here would render
    as "$0.00" on a page next to real usage.
    """
    lines: list[InvoiceLine] = []

    flat = price_cents(plan, interval)
    if flat is not None:
        lines.append(
            InvoiceLine(
                kind="subscription",
                dimension=None,
                description=f"{plan.display_name} plan ({interval.value})",
                quantity=1,
                unit_label="plan",
                amount_cents=flat,
            )
        )

    for dimension in MeteredDimension:
        line = _overage_line(plan=plan, dimension=dimension, used=usage.quantity(dimension))
        if line is not None:
            lines.append(line)

    return DraftInvoice(
        workspace_id=usage.workspace_id,
        period_start=usage.period_start,
        period_end=usage.period_end,
        currency=plan.currency,
        lines=lines,
        # The single conversion point. Called once per invoice over the
        # summed micro-USD, never per event — rounding each of thousands
        # of sub-cent LLM calls to whole cents would round nearly all of
        # them to zero.
        platform_cost_cents=micro_usd_to_cents(usage.total_cost_micro_usd),
    )
