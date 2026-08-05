"""Metered usage: what gets recorded, and how a period's total is
derived from it.

Pure — no I/O. The arithmetic here decides what a customer is billed, so
CLAUDE.md §11 requires it be testable without Postgres.

**Every dimension maps to a countable event the platform already
records.** `saas-strategist`'s rule is that a metered dimension is never
a fuzzy "usage unit": an agent run is a row in `agent_runs`, a token
count comes from the provider's own response, an MCP call is a row the
tool-execution boundary already writes. The mapping lives in
`UsageSource` below and is asserted by a test rather than left to a
docstring.

**Two units, one conversion point.** `quantity` is whatever the
dimension counts — runs, tokens, megabytes. `cost_micro_usd` is what the
platform actually paid a provider for it, in the micro-USD unit
`agentverse_shared.cost_accounting` established (a single LLM call
routinely costs a fraction of a cent, and rounding per call would round
most of them to zero). Neither is money owed. What a customer owes is
computed from the plan's allowances and overage rates at invoice time,
in integer cents, and `cost_micro_usd` exists so margin is answerable —
not so it can be charged directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from agentverse_api.billing_service.domain.plan import MeteredDimension


class UsageSource(StrEnum):
    """Where a usage event came from.

    Recorded per event so an unexpected invoice line can be traced back
    to the subsystem that produced it. A total nobody can attribute is a
    total nobody can dispute or defend.
    """

    AGENT_RUN = "agent_run"
    TEAM_SESSION = "team_session"
    TOOL_CALL = "tool_call"
    WORKFLOW = "workflow"
    BACKGROUND_JOB = "background_job"
    API_REQUEST = "api_request"
    STORAGE_SNAPSHOT = "storage_snapshot"


#: Which subsystem is the durable source for each metered dimension.
#:
#: This is the "reconciliation rule" `saas-strategist` requires per
#: dimension: if a dimension is not in this mapping, nothing in the
#: platform produces it and its allowance would always read as unused —
#: a plan limit that silently never applies. A test asserts the mapping
#: covers every member of `MeteredDimension`.
DIMENSION_SOURCES: dict[MeteredDimension, UsageSource] = {
    MeteredDimension.AGENT_RUNS: UsageSource.AGENT_RUN,
    MeteredDimension.TOKENS: UsageSource.AGENT_RUN,
    MeteredDimension.MCP_CALLS: UsageSource.TOOL_CALL,
    MeteredDimension.WORKFLOW_EXECUTIONS: UsageSource.WORKFLOW,
    MeteredDimension.BACKGROUND_JOBS: UsageSource.BACKGROUND_JOB,
    MeteredDimension.API_CALLS: UsageSource.API_REQUEST,
    MeteredDimension.BANDWIDTH_MB: UsageSource.API_REQUEST,
    MeteredDimension.KNOWLEDGE_STORAGE_MB: UsageSource.STORAGE_SNAPSHOT,
    MeteredDimension.VECTOR_STORAGE_MB: UsageSource.STORAGE_SNAPSHOT,
}

#: Dimensions that are a *level*, not an accumulation.
#:
#: Storage is the odd one out: a workspace holding 5 GB all month used
#: 5 GB, not 150 GB-days. Summing storage snapshots the way runs are
#: summed would multiply a customer's storage bill by the number of times
#: the snapshot job ran, which is a configuration detail they never
#: agreed to be billed by. These take the maximum observed value in the
#: period instead.
LEVEL_DIMENSIONS: frozenset[MeteredDimension] = frozenset(
    {MeteredDimension.KNOWLEDGE_STORAGE_MB, MeteredDimension.VECTOR_STORAGE_MB}
)


class InvalidUsageError(ValueError):
    """A usage event that cannot be recorded as given.

    Raised rather than clamped or dropped. A negative quantity, or one
    for a dimension nothing produces, means an upstream bug — and
    silently coercing it to zero would hide the bug while quietly
    under-billing.
    """


@dataclass(frozen=True, slots=True)
class UsageEvent:
    """One recorded unit of metered usage.

    `idempotency_key` is what makes recording safe under retry. A worker
    that crashes after recording but before acknowledging its job will
    re-run and re-record; without a natural key, the workspace is billed
    twice for work done once. The key is derived from the source row —
    `run:{run_id}:tokens`, not a random uuid — so the second attempt
    produces the same key rather than a new one.
    """

    workspace_id: str
    dimension: MeteredDimension
    quantity: int
    occurred_at: datetime
    source: UsageSource
    source_id: str | None
    idempotency_key: str
    #: What the platform paid a provider, if this event had a provider
    #: cost. `None` for dimensions with no direct provider cost (an API
    #: request, a workflow execution).
    cost_micro_usd: int | None = None

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise InvalidUsageError(
                f"quantity must not be negative for {self.dimension.value}, got {self.quantity}"
            )
        if self.cost_micro_usd is not None and self.cost_micro_usd < 0:
            raise InvalidUsageError(
                f"cost_micro_usd must not be negative, got {self.cost_micro_usd}"
            )
        if not self.idempotency_key:
            raise InvalidUsageError(
                "every usage event needs an idempotency key derived from its source row; "
                "without one a retried worker bills the same work twice"
            )


@dataclass(frozen=True, slots=True)
class DimensionUsage:
    """One dimension's total for one billing period."""

    dimension: MeteredDimension
    quantity: int
    cost_micro_usd: int

    @property
    def is_level(self) -> bool:
        return self.dimension in LEVEL_DIMENSIONS


@dataclass(frozen=True, slots=True)
class PeriodUsage:
    """Everything a workspace used in one billing period.

    Carries the period boundaries, not just the numbers: a total with no
    period attached cannot be checked against an invoice, and "usage this
    month" and "usage this billing period" are different questions for
    every customer whose period does not start on the 1st.
    """

    workspace_id: str
    period_start: datetime
    period_end: datetime
    dimensions: dict[MeteredDimension, DimensionUsage]

    def quantity(self, dimension: MeteredDimension) -> int:
        """Zero for a dimension with no recorded events — the true count,
        not a missing value. Every dimension always has an answer.
        """
        usage = self.dimensions.get(dimension)
        return 0 if usage is None else usage.quantity

    def cost_micro_usd(self, dimension: MeteredDimension) -> int:
        usage = self.dimensions.get(dimension)
        return 0 if usage is None else usage.cost_micro_usd

    @property
    def total_cost_micro_usd(self) -> int:
        """What the platform paid across every dimension this period.

        Margin input, never an amount charged. Converting this to cents
        and invoicing it would bill a customer our supplier costs rather
        than our published prices.
        """
        return sum(usage.cost_micro_usd for usage in self.dimensions.values())

    def as_quantities(self) -> dict[MeteredDimension, int]:
        """The shape the entitlement lines consume."""
        return {dimension: usage.quantity for dimension, usage in self.dimensions.items()}


def combine(dimension: MeteredDimension, quantities: list[int]) -> int:
    """Fold a dimension's recorded values into its period total.

    Sum for accumulating dimensions, maximum for level dimensions. The
    distinction is the whole reason this is a function rather than an
    inline `sum()`: summing storage snapshots would multiply a customer's
    storage bill by however often the snapshot job happened to run.
    """
    if not quantities:
        return 0
    if dimension in LEVEL_DIMENSIONS:
        return max(quantities)
    return sum(quantities)
