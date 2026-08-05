"""Recording metered usage, and answering "how much has this workspace
used this period".

Two responsibilities that `billing-expert` requires be kept separate and
individually testable: **aggregation** (computing totals from events)
lives here; **invoice generation** (turning totals into billable lines)
lives in `invoicing_service.py`. Collapsing them would make it impossible
to test that a total is right without also asserting a price.

**The billing period is the subscription's, not the calendar month.** A
workspace that subscribed on the 17th is billed the 17th to the 17th, and
aggregating by calendar month would split its usage across two invoices.
A workspace with no subscription is on Free and gets a calendar-month
window, because there is no subscription period to borrow.

**Recording never fails a caller's request.** A run that completed
successfully must not be reported as failed because the usage write hit a
constraint — the customer got the work. Failures are logged and left for
reconciliation, which is the honest trade: under-recording is a revenue
problem the platform can detect, while failing a completed run is a
correctness problem the customer sees.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from agentverse_api.billing_service.application.subscription_service import (
    SubscriptionService,
    add_months,
)
from agentverse_api.billing_service.domain.plan import MeteredDimension
from agentverse_api.billing_service.domain.ports import UsageRepository
from agentverse_api.billing_service.domain.usage import (
    PeriodUsage,
    UsageEvent,
    UsageSource,
)

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def calendar_month_bounds(moment: datetime) -> tuple[datetime, datetime]:
    """The calendar month containing `moment`.

    Used only for workspaces with no subscription. A Free workspace has
    no billing period of its own, and inventing one from its signup date
    would make its quota reset on a day it has no reason to expect.
    """
    start = moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, add_months(start, 1)


@dataclass(slots=True)
class UsageService:
    usage: UsageRepository
    subscriptions: SubscriptionService
    now: Callable[[], datetime] = field(default=_utc_now)

    # ---- recording ---------------------------------------------------

    async def record(self, events: list[UsageEvent]) -> int:
        """Append usage. Returns how many rows were new.

        A return below `len(events)` is not an error — it means a retried
        worker re-submitted work already recorded, which is exactly what
        the idempotency key is for.
        """
        if not events:
            return 0
        return await self.usage.record(events)

    async def record_run(
        self,
        *,
        workspace_id: str,
        run_id: str,
        tokens: int,
        cost_micro_usd: int,
        occurred_at: datetime | None = None,
    ) -> int:
        """The common case: one finished agent run, two dimensions.

        Both events derive their idempotency key from `run_id`, so a
        worker that crashes between recording and acknowledging re-runs
        and produces the same keys rather than a second charge. Emitted
        together in one call because they are one fact — a run that
        counted its tokens but not itself would show usage no allowance
        was consumed by.
        """
        at = occurred_at or self.now()
        return await self.record(
            [
                UsageEvent(
                    workspace_id=workspace_id,
                    dimension=MeteredDimension.AGENT_RUNS,
                    quantity=1,
                    occurred_at=at,
                    source=UsageSource.AGENT_RUN,
                    source_id=run_id,
                    idempotency_key=f"run:{run_id}:agent_runs",
                    # The run's provider cost is attributed to the tokens
                    # line, not counted twice here.
                    cost_micro_usd=None,
                ),
                UsageEvent(
                    workspace_id=workspace_id,
                    dimension=MeteredDimension.TOKENS,
                    quantity=tokens,
                    occurred_at=at,
                    source=UsageSource.AGENT_RUN,
                    source_id=run_id,
                    idempotency_key=f"run:{run_id}:tokens",
                    cost_micro_usd=cost_micro_usd,
                ),
            ]
        )

    async def record_quietly(self, events: list[UsageEvent]) -> None:
        """Record, swallowing failures.

        For call sites on a completed-work path. A run that finished must
        not be reported as failed because the usage write hit a
        constraint — the customer got the work, and under-recording is a
        revenue problem reconciliation can find, while failing a
        completed run is a correctness problem the customer sees
        immediately.
        """
        try:
            await self.record(events)
        except Exception:
            logger.exception(
                "billing_usage_record_failed",
                extra={"workspace_id": events[0].workspace_id if events else None},
            )

    # ---- reading -----------------------------------------------------

    async def current_period_bounds(self, workspace_id: str) -> tuple[datetime, datetime]:
        """The window quota and usage are measured over.

        The subscription's period when there is one — a workspace that
        subscribed on the 17th is billed the 17th to the 17th, and using
        calendar months would split its usage across two invoices.
        """
        subscription = await self.subscriptions.current(workspace_id)
        if subscription is None:
            return calendar_month_bounds(self.now())
        return subscription.current_period_start, subscription.current_period_end

    async def current_period_usage(self, workspace_id: str) -> PeriodUsage:
        """Live totals, straight from the event rows.

        Deliberately not the rollups: those are frozen at period close,
        and the usage panel has to move as work happens.
        """
        start, end = await self.current_period_bounds(workspace_id)
        return await self.usage.usage_for_period(
            workspace_id=workspace_id, period_start=start, period_end=end
        )

    # ---- aggregation -------------------------------------------------

    async def aggregate_period(
        self, *, workspace_id: str, period_start: datetime, period_end: datetime
    ) -> PeriodUsage:
        """Recompute and store a period's rollups, without finalizing.

        Safe to run repeatedly: the rollup key is
        `(workspace_id, period_start, dimension)`, so a re-run recomputes
        the same rows rather than adding a second set. Running it during
        an open period keeps the stored totals warm without committing
        to them.
        """
        usage = await self.usage.usage_for_period(
            workspace_id=workspace_id, period_start=period_start, period_end=period_end
        )
        await self.usage.write_rollups(
            workspace_id=workspace_id,
            period_start=period_start,
            period_end=period_end,
            usage=usage,
            finalize=False,
        )
        return usage

    async def finalize_period(
        self, *, workspace_id: str, period_start: datetime, period_end: datetime
    ) -> PeriodUsage:
        """Close a period: recompute, then freeze.

        Recomputes rather than trusting whatever the last incremental run
        stored — `billing-expert`'s reconciliation step, and the reason
        it is a second pass over the same events rather than an
        incremental add. If the two disagree, the recomputation is right,
        because it reads every event the period actually contains.

        Refuses to finalize a period that has not ended: freezing totals
        while work is still landing would bill a period in progress.
        """
        moment = self.now()
        if moment < period_end:
            raise ValueError(
                f"Refusing to finalize a billing period that ends at "
                f"{period_end.isoformat()} — it is still open at {moment.isoformat()}"
            )
        usage = await self.usage.usage_for_period(
            workspace_id=workspace_id, period_start=period_start, period_end=period_end
        )
        await self.usage.write_rollups(
            workspace_id=workspace_id,
            period_start=period_start,
            period_end=period_end,
            usage=usage,
            finalize=True,
        )
        return usage

    async def reconcile_period(
        self, *, workspace_id: str, period_start: datetime, period_end: datetime
    ) -> dict[MeteredDimension, tuple[int, int]]:
        """Compare stored rollups against a fresh scan of the events.

        `{dimension: (rollup_quantity, event_quantity)}` for every
        dimension where they disagree — empty when they match.
        `billing-expert`'s standing requirement: a scheduled check that
        invoiced totals still equal the raw event sums, because metering
        drift is otherwise silent until a customer disputes a charge.
        """
        stored = await self.usage.finalized_rollups(
            workspace_id=workspace_id, period_start=period_start
        )
        if stored is None:
            return {}
        fresh = await self.usage.usage_for_period(
            workspace_id=workspace_id, period_start=period_start, period_end=period_end
        )
        drift: dict[MeteredDimension, tuple[int, int]] = {}
        for dimension in MeteredDimension:
            recorded = stored.quantity(dimension)
            actual = fresh.quantity(dimension)
            if recorded != actual:
                drift[dimension] = (recorded, actual)
        return drift
