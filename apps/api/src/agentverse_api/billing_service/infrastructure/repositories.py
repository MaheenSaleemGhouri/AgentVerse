"""Postgres adapters for the billing domain's ports."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.auth_service.infrastructure.repositories import SqlWorkspaceRepository
from agentverse_api.billing_service.domain.customer import BillingCustomer, PaymentProvider
from agentverse_api.billing_service.domain.entitlements import ResourceUsage
from agentverse_api.billing_service.domain.plan import (
    BillingInterval,
    MeteredDimension,
    Plan,
    PlanTier,
    tier_rank,
)
from agentverse_api.billing_service.domain.subscription import (
    Subscription,
    SubscriptionStatus,
    SubscriptionTrigger,
)
from agentverse_api.billing_service.domain.usage import (
    LEVEL_DIMENSIONS,
    DimensionUsage,
    PeriodUsage,
    UsageEvent,
)
from agentverse_api.billing_service.infrastructure import plan_config
from agentverse_api.billing_service.infrastructure.models import (
    BillingCustomerModel,
    BillingSubscriptionModel,
    PlanModel,
    SubscriptionEventModel,
    UsageEventModel,
    UsageRollupModel,
    WebhookEventModel,
)
from agentverse_api.orchestration_service.infrastructure.integration_repository import (
    SqlIntegrationRepository,
)
from agentverse_api.orchestration_service.infrastructure.knowledge_repository import (
    SqlKnowledgeRepository,
)
from agentverse_api.orchestration_service.infrastructure.repositories import SqlAgentRepository
from agentverse_api.orchestration_service.infrastructure.team_repository import SqlTeamRepository


def _to_plan(row: PlanModel) -> Plan:
    return plan_config.to_domain(
        plan_id=row.id,
        slug=row.slug,
        display_name=row.display_name,
        description=row.description,
        monthly_price_cents=row.monthly_price_cents,
        annual_price_cents=row.annual_price_cents,
        currency=row.currency,
        trial_days=row.trial_days,
        is_public=row.is_public,
        is_active=row.is_active,
        sort_order=row.sort_order,
        resource_limits=row.resource_limits,
        metered_allowances=row.metered_allowances,
        capabilities=row.capabilities,
        overage_rates=row.overage_rates,
        api_rate_limit_per_minute=row.api_rate_limit_per_minute,
    )


class SqlPlanRepository:
    """Implements `domain.ports.PlanRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self, *, public_only: bool) -> list[Plan]:
        stmt = select(PlanModel).where(PlanModel.is_active.is_(True))
        if public_only:
            stmt = stmt.where(PlanModel.is_public.is_(True))
        result = await self._session.execute(stmt)
        plans = [_to_plan(row) for row in result.scalars().all()]
        # Sorted in Python by (sort_order, tier rank) rather than in SQL,
        # because tier rank is a domain fact — the ordering of FREE
        # through ENTERPRISE — and encoding it as a CASE expression in
        # the query would be a second copy of it that a later tier
        # addition could forget to update.
        plans.sort(key=lambda plan: (plan.sort_order, tier_rank(plan.slug)))
        return plans

    async def get_by_slug(self, slug: PlanTier) -> Plan | None:
        result = await self._session.execute(
            select(PlanModel).where(
                PlanModel.slug == slug,
                PlanModel.is_active.is_(True),
            )
        )
        row = result.scalar_one_or_none()
        return None if row is None else _to_plan(row)


def _to_subscription(row: BillingSubscriptionModel, plan_slug: PlanTier) -> Subscription:
    return Subscription(
        id=row.id,
        workspace_id=row.workspace_id,
        plan_id=row.plan_id,
        plan_slug=plan_slug,
        status=SubscriptionStatus(row.status),
        interval=BillingInterval(row.billing_interval),
        current_period_start=row.current_period_start,
        current_period_end=row.current_period_end,
        trial_end=row.trial_end,
        cancel_at_period_end=row.cancel_at_period_end,
        canceled_at=row.canceled_at,
        past_due_since=row.past_due_since,
        provider_subscription_id=row.provider_subscription_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


#: Columns `record_transition` is allowed to write alongside a status
#: change. An explicit allowlist rather than `setattr` over whatever the
#: caller passed: `changes` originates several layers up, and without
#: this a typo'd key would be silently ignored while a well-chosen one
#: could rewrite `workspace_id` and move a subscription between tenants.
_MUTABLE_ON_TRANSITION: frozenset[str] = frozenset(
    {
        "current_period_start",
        "current_period_end",
        "trial_end",
        "cancel_at_period_end",
        "canceled_at",
        "past_due_since",
        "provider_subscription_id",
    }
)


class UnknownSubscriptionFieldError(KeyError):
    """`changes` named a column that is not writable on a transition."""


class SqlSubscriptionRepository:
    """Implements `domain.ports.SubscriptionRepository`.

    Writes only; it does not commit. The unit of work is the request's
    session (the same convention the other contexts' repositories
    follow), so a transition and whatever else the use case does land in
    one transaction or not at all.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _row_with_slug(
        self, subscription_id: str
    ) -> tuple[BillingSubscriptionModel, PlanTier] | None:
        result = await self._session.execute(
            select(BillingSubscriptionModel, PlanModel.slug)
            .join(PlanModel, PlanModel.id == BillingSubscriptionModel.plan_id)
            .where(BillingSubscriptionModel.id == subscription_id)
        )
        row = result.one_or_none()
        return None if row is None else (row[0], row[1])

    async def get_for_workspace(self, workspace_id: str) -> Subscription | None:
        # Excludes canceled rows: "what is this workspace on right now"
        # has one answer, and the partial unique index guarantees at most
        # one non-canceled row exists to return.
        result = await self._session.execute(
            select(BillingSubscriptionModel, PlanModel.slug)
            .join(PlanModel, PlanModel.id == BillingSubscriptionModel.plan_id)
            .where(
                BillingSubscriptionModel.workspace_id == workspace_id,
                BillingSubscriptionModel.status != SubscriptionStatus.CANCELED.value,
            )
        )
        row = result.one_or_none()
        return None if row is None else _to_subscription(row[0], row[1])

    async def get_by_id(self, subscription_id: str) -> Subscription | None:
        found = await self._row_with_slug(subscription_id)
        return None if found is None else _to_subscription(*found)

    async def create(
        self,
        *,
        workspace_id: str,
        plan_id: str,
        status: SubscriptionStatus,
        interval: BillingInterval,
        current_period_start: datetime,
        current_period_end: datetime,
        trial_end: datetime | None,
        provider_subscription_id: str | None,
        idempotency_key: str,
        actor: str,
    ) -> Subscription:
        subscription_id = str(uuid.uuid4())
        self._session.add(
            BillingSubscriptionModel(
                id=subscription_id,
                workspace_id=workspace_id,
                plan_id=plan_id,
                status=status.value,
                billing_interval=interval.value,
                current_period_start=current_period_start,
                current_period_end=current_period_end,
                trial_end=trial_end,
                provider_subscription_id=provider_subscription_id,
            )
        )
        # Creation is itself a transition — from nothing to the opening
        # status — and gets an event row for the same reason every other
        # one does: the history has to start somewhere, and a
        # subscription whose first event is its second transition cannot
        # be reconciled.
        self._session.add(
            SubscriptionEventModel(
                id=str(uuid.uuid4()),
                subscription_id=subscription_id,
                workspace_id=workspace_id,
                trigger=SubscriptionTrigger.TRIAL_STARTED.value
                if status is SubscriptionStatus.TRIALING
                else SubscriptionTrigger.PAYMENT_SUCCEEDED.value,
                from_status=status.value,
                to_status=status.value,
                actor=actor,
                reason="subscription created",
                idempotency_key=idempotency_key,
                event_metadata={"plan_id": plan_id, "interval": interval.value},
            )
        )
        await self._session.flush()
        found = await self._row_with_slug(subscription_id)
        assert found is not None  # noqa: S101 - just inserted in this session
        return _to_subscription(*found)

    async def record_transition(
        self,
        *,
        subscription_id: str,
        trigger: SubscriptionTrigger,
        from_status: SubscriptionStatus,
        to_status: SubscriptionStatus,
        idempotency_key: str,
        actor: str,
        reason: str | None,
        metadata: dict[str, object],
        changes: dict[str, object],
    ) -> Subscription:
        found = await self._row_with_slug(subscription_id)
        if found is None:
            raise LookupError(f"No subscription {subscription_id!r}")
        row, _ = found
        unknown = set(changes) - _MUTABLE_ON_TRANSITION
        if unknown:
            raise UnknownSubscriptionFieldError(f"not writable on a transition: {sorted(unknown)}")
        row.status = to_status.value
        for field, value in changes.items():
            setattr(row, field, value)
        self._session.add(
            SubscriptionEventModel(
                id=str(uuid.uuid4()),
                subscription_id=subscription_id,
                workspace_id=row.workspace_id,
                trigger=trigger.value,
                from_status=from_status.value,
                to_status=to_status.value,
                actor=actor,
                reason=reason,
                idempotency_key=idempotency_key,
                event_metadata=metadata,
            )
        )
        await self._session.flush()
        refreshed = await self._row_with_slug(subscription_id)
        assert refreshed is not None  # noqa: S101 - loaded above
        return _to_subscription(*refreshed)

    async def set_cancel_at_period_end(
        self, *, subscription_id: str, cancel_at_period_end: bool
    ) -> Subscription:
        found = await self._row_with_slug(subscription_id)
        if found is None:
            raise LookupError(f"No subscription {subscription_id!r}")
        row, slug = found
        row.cancel_at_period_end = cancel_at_period_end
        await self._session.flush()
        return _to_subscription(row, slug)

    async def change_plan(
        self, *, subscription_id: str, plan_id: str, interval: BillingInterval
    ) -> Subscription:
        found = await self._row_with_slug(subscription_id)
        if found is None:
            raise LookupError(f"No subscription {subscription_id!r}")
        row, _ = found
        row.plan_id = plan_id
        row.billing_interval = interval.value
        await self._session.flush()
        refreshed = await self._row_with_slug(subscription_id)
        assert refreshed is not None  # noqa: S101 - loaded above
        return _to_subscription(*refreshed)

    async def find_event_by_idempotency_key(self, key: str) -> str | None:
        result = await self._session.execute(
            select(SubscriptionEventModel.subscription_id).where(
                SubscriptionEventModel.idempotency_key == key
            )
        )
        return result.scalar_one_or_none()

    async def list_events(
        self, *, subscription_id: str, limit: int
    ) -> list[tuple[str, str, str, str, datetime]]:
        result = await self._session.execute(
            select(
                SubscriptionEventModel.trigger,
                SubscriptionEventModel.from_status,
                SubscriptionEventModel.to_status,
                SubscriptionEventModel.actor,
                SubscriptionEventModel.occurred_at,
            )
            .where(SubscriptionEventModel.subscription_id == subscription_id)
            .order_by(SubscriptionEventModel.occurred_at.desc())
            .limit(limit)
        )
        return [(row[0], row[1], row[2], row[3], row[4]) for row in result.all()]


class SqlUsageRepository:
    """Implements `domain.ports.UsageRepository`.

    Every query filters on `workspace_id` and a period range, matching
    `ix_billing_usage_events_workspace_period` — the index the table was
    designed around. Aggregation happens in Postgres rather than by
    pulling rows into Python: a busy workspace produces tens of thousands
    of events per period, and fetching them to sum would move the whole
    period over the wire to compute nine numbers.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, events: list[UsageEvent]) -> int:
        if not events:
            return 0
        # One multi-row INSERT with ON CONFLICT DO NOTHING, not a
        # row-by-row loop: the natural unit is a finished run emitting
        # several dimensions at once, and the conflict clause is what
        # makes a retried worker a no-op rather than a double charge.
        stmt = (
            pg_insert(UsageEventModel)
            .values(
                [
                    {
                        "id": str(uuid.uuid4()),
                        "occurred_at": event.occurred_at,
                        "workspace_id": event.workspace_id,
                        "dimension": event.dimension.value,
                        "source": event.source.value,
                        "source_id": event.source_id,
                        "quantity": event.quantity,
                        "cost_micro_usd": event.cost_micro_usd,
                        "idempotency_key": event.idempotency_key,
                        "event_metadata": {},
                    }
                    for event in events
                ]
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key", "occurred_at"])
            .returning(UsageEventModel.id)
        )
        result = await self._session.execute(stmt)
        return len(result.scalars().all())

    async def usage_for_period(
        self, *, workspace_id: str, period_start: datetime, period_end: datetime
    ) -> PeriodUsage:
        # `sum` and `max` are both computed for every dimension, and the
        # domain picks which one applies. Doing it here rather than
        # branching in SQL keeps the accumulate-vs-level rule in exactly
        # one place — `usage.LEVEL_DIMENSIONS` — instead of splitting it
        # across a query and a module.
        result = await self._session.execute(
            select(
                UsageEventModel.dimension,
                func.sum(UsageEventModel.quantity),
                func.max(UsageEventModel.quantity),
                func.coalesce(func.sum(UsageEventModel.cost_micro_usd), 0),
            )
            .where(
                UsageEventModel.workspace_id == workspace_id,
                UsageEventModel.occurred_at >= period_start,
                UsageEventModel.occurred_at < period_end,
            )
            .group_by(UsageEventModel.dimension)
        )
        dimensions: dict[MeteredDimension, DimensionUsage] = {}
        for raw_dimension, total, peak, cost in result.all():
            try:
                dimension = MeteredDimension(raw_dimension)
            except ValueError:
                # A dimension this build does not know — a row written by
                # a newer deploy during a rollout. Skipped rather than
                # crashing the usage panel; the aggregation job on the
                # newer build will account for it.
                continue
            quantity = int(peak or 0) if dimension in LEVEL_DIMENSIONS else int(total or 0)
            dimensions[dimension] = DimensionUsage(
                dimension=dimension, quantity=quantity, cost_micro_usd=int(cost or 0)
            )
        return PeriodUsage(
            workspace_id=workspace_id,
            period_start=period_start,
            period_end=period_end,
            dimensions=dimensions,
        )

    async def write_rollups(
        self,
        *,
        workspace_id: str,
        period_start: datetime,
        period_end: datetime,
        usage: PeriodUsage,
        finalize: bool,
    ) -> None:
        if not usage.dimensions:
            return
        finalized_at = datetime.now(UTC) if finalize else None
        stmt = (
            pg_insert(UsageRollupModel)
            .values(
                [
                    {
                        "id": str(uuid.uuid4()),
                        "workspace_id": workspace_id,
                        "period_start": period_start,
                        "period_end": period_end,
                        "dimension": dimension.value,
                        "quantity": row.quantity,
                        "cost_micro_usd": row.cost_micro_usd,
                        "finalized_at": finalized_at,
                    }
                    for dimension, row in usage.dimensions.items()
                ]
            )
            .on_conflict_do_update(
                index_elements=["workspace_id", "period_start", "dimension"],
                set_={
                    "quantity": text("excluded.quantity"),
                    "cost_micro_usd": text("excluded.cost_micro_usd"),
                    "period_end": text("excluded.period_end"),
                    "finalized_at": text("excluded.finalized_at"),
                    "computed_at": func.now(),
                },
            )
        )
        await self._session.execute(stmt)

    async def finalized_rollups(
        self, *, workspace_id: str, period_start: datetime
    ) -> PeriodUsage | None:
        result = await self._session.execute(
            select(UsageRollupModel).where(
                UsageRollupModel.workspace_id == workspace_id,
                UsageRollupModel.period_start == period_start,
                UsageRollupModel.finalized_at.is_not(None),
            )
        )
        rows = list(result.scalars().all())
        if not rows:
            return None
        dimensions: dict[MeteredDimension, DimensionUsage] = {}
        for row in rows:
            try:
                dimension = MeteredDimension(row.dimension)
            except ValueError:
                continue
            dimensions[dimension] = DimensionUsage(
                dimension=dimension,
                quantity=row.quantity,
                cost_micro_usd=row.cost_micro_usd,
            )
        return PeriodUsage(
            workspace_id=workspace_id,
            period_start=period_start,
            period_end=rows[0].period_end,
            dimensions=dimensions,
        )


class SqlWebhookEventRepository:
    """Implements `domain.ports.WebhookEventRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(
        self,
        *,
        provider: str,
        provider_event_id: str,
        event_type: str,
        workspace_id: str | None,
    ) -> bool:
        # ON CONFLICT DO NOTHING, not select-then-insert: two deliveries
        # of the same event can be in flight at once, and the read-then-
        # write version lets both pass the check before either writes.
        # The unique index decides, and the loser is told it lost.
        stmt = (
            pg_insert(WebhookEventModel)
            .values(
                id=str(uuid.uuid4()),
                provider=provider,
                provider_event_id=provider_event_id,
                event_type=event_type,
                workspace_id=workspace_id,
                status="received",
            )
            .on_conflict_do_nothing(
                index_elements=[
                    WebhookEventModel.provider,
                    WebhookEventModel.provider_event_id,
                ]
            )
            .returning(WebhookEventModel.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def resolve(
        self,
        *,
        provider: str,
        provider_event_id: str,
        status: str,
        error: str | None,
    ) -> None:
        await self._session.execute(
            update(WebhookEventModel)
            .where(
                WebhookEventModel.provider == provider,
                WebhookEventModel.provider_event_id == provider_event_id,
            )
            .values(status=status, error=error, processed_at=func.now())
        )

    async def was_processed(self, *, provider: str, provider_event_id: str) -> bool:
        result = await self._session.execute(
            select(WebhookEventModel.status).where(
                WebhookEventModel.provider == provider,
                WebhookEventModel.provider_event_id == provider_event_id,
            )
        )
        status = result.scalar_one_or_none()
        return status in ("processed", "ignored")


class SqlCustomerRepository:
    """Implements `domain.ports.CustomerRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_workspace(self, workspace_id: str) -> BillingCustomer | None:
        result = await self._session.execute(
            select(BillingCustomerModel).where(BillingCustomerModel.workspace_id == workspace_id)
        )
        row = result.scalar_one_or_none()
        return None if row is None else self._to_domain(row)

    async def upsert(
        self,
        *,
        workspace_id: str,
        provider: PaymentProvider,
        provider_customer_id: str,
        billing_email: str | None,
    ) -> BillingCustomer:
        # ON CONFLICT rather than select-then-insert: the caller is
        # usually reacting to a processor event that can be delivered
        # twice concurrently, and the read-then-write version loses that
        # race by creating a second row the unique index then rejects
        # with a 500 instead of succeeding idempotently.
        stmt = (
            pg_insert(BillingCustomerModel)
            .values(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                provider=provider.value,
                provider_customer_id=provider_customer_id,
                billing_email=billing_email,
            )
            .on_conflict_do_update(
                index_elements=[BillingCustomerModel.workspace_id],
                set_={
                    "provider_customer_id": provider_customer_id,
                    "billing_email": billing_email,
                },
            )
            .returning(BillingCustomerModel)
        )
        result = await self._session.execute(stmt)
        return self._to_domain(result.scalar_one())

    @staticmethod
    def _to_domain(row: BillingCustomerModel) -> BillingCustomer:
        return BillingCustomer(
            id=row.id,
            workspace_id=row.workspace_id,
            provider=PaymentProvider(row.provider),
            provider_customer_id=row.provider_customer_id,
            billing_email=row.billing_email,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class SqlWorkspaceUsageRepository:
    """Implements `domain.ports.WorkspaceUsageRepository` by asking each
    owning context for its own count.

    Every count is one indexed aggregate on `(workspace_id, …)`, and they
    are issued together rather than one at a time — five sequential round
    trips to render one usage panel is the N+1 this shape exists to avoid.
    They share a single `AsyncSession`, which is not concurrency-safe, so
    "together" means sequentially on one connection; the win is that the
    caller makes one call, not that the queries overlap.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._agents = SqlAgentRepository(session)
        self._teams = SqlTeamRepository(session)
        self._knowledge = SqlKnowledgeRepository(session)
        self._integrations = SqlIntegrationRepository(session)
        self._workspaces = SqlWorkspaceRepository(session)

    async def resource_usage(self, workspace_id: str) -> ResourceUsage:
        return ResourceUsage(
            agents=await self._agents.count_for_workspace(workspace_id),
            teams=await self._teams.count_teams(workspace_id=workspace_id),
            knowledge_bases=await self._knowledge.count_knowledge_bases(workspace_id=workspace_id),
            mcp_connections=await self._integrations.count_installed(workspace_id=workspace_id),
            seats=await self._workspaces.count_members(workspace_id),
        )
