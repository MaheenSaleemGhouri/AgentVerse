"""Billing ORM models.

`plans` is the catalog — the single row set that both the pricing page
and server-side entitlement enforcement read (Rule 3, and
`saas-pricing-expert`'s "pricing configuration is the single source"
requirement). Putting it in Postgres rather than a Python constant is
what makes "plans must be configurable from the backend" true: changing
a limit or a price is an UPDATE plus a cache bust, not a deploy.

The limit/allowance/capability/overage columns are `jsonb` validated by
an application-layer Pydantic schema, following CLAUDE.md §8's
`agents.config` precedent: the database stores flexibility, the API
enforces shape. The alternative — a column per dimension — would mean a
migration every time a new metered dimension is added, and there are
nine of them already.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from agentverse_api.billing_service.domain.plan import PlanTier
from agentverse_api.infrastructure.orm_base import Base

_SUBSCRIPTION_STATUSES = ("trialing", "active", "past_due", "paused", "canceled")


class PlanTierType(TypeDecorator[PlanTier]):
    """TEXT in the database, `PlanTier` in Python.

    TEXT + CHECK rather than a Postgres ENUM, for the same reversibility
    reason the role columns moved off `workspace_role` in migration
    `b3f7c1a9e582`: `ALTER TYPE ... DROP VALUE` does not exist, so an
    enum makes any migration that adds a tier irreversible, and Rule 19
    requires a working `downgrade()`.

    Coercing here rather than in each row converter keeps `Mapped[PlanTier]`
    honest — without it SQLAlchemy hands back bare strings and
    `slug is PlanTier.FREE` quietly starts returning False while `==`
    keeps working.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: PlanTier | str | None, dialect: object) -> str | None:
        if value is None:
            return None
        return PlanTier(value).value

    def process_result_value(self, value: str | None, dialect: object) -> PlanTier | None:
        if value is None:
            return None
        return PlanTier(value)


class PlanModel(Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint(
            "slug IN ('free', 'pro', 'team', 'enterprise')",
            name="ck_plans_slug",
        ),
        # A published price of exactly zero is meaningful (Free); a
        # negative one never is, and would flow straight into an invoice
        # line as a credit nobody granted.
        CheckConstraint(
            "monthly_price_cents IS NULL OR monthly_price_cents >= 0",
            name="ck_plans_monthly_price_non_negative",
        ),
        CheckConstraint(
            "annual_price_cents IS NULL OR annual_price_cents >= 0",
            name="ck_plans_annual_price_non_negative",
        ),
        CheckConstraint("trial_days >= 0", name="ck_plans_trial_days_non_negative"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Unique: a tier resolves to exactly one catalog row. Superseding a
    # plan means editing this row or deactivating it and inserting a new
    # tier, never keeping two rows for `pro` and hoping callers pick the
    # right one.
    slug: Mapped[PlanTier] = mapped_column(PlanTierType, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    # NULL means "not published" — Enterprise is quoted, not priced. It
    # is not the same as 0, which is Free's real, published price.
    monthly_price_cents: Mapped[int | None] = mapped_column(default=None)
    annual_price_cents: Mapped[int | None] = mapped_column(default=None)
    currency: Mapped[str] = mapped_column(Text, default="usd")
    trial_days: Mapped[int] = mapped_column(default=0)
    # A plan can be active (enforced for workspaces on it) yet not public
    # (withdrawn from sale). Two booleans, because collapsing them into
    # one status would make grandfathering impossible to express.
    is_public: Mapped[bool] = mapped_column(default=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    resource_limits: Mapped[dict[str, int | None]] = mapped_column(JSONB, default=dict)
    metered_allowances: Mapped[dict[str, int | None]] = mapped_column(JSONB, default=dict)
    capabilities: Mapped[list[str]] = mapped_column(JSONB, default=list)
    overage_rates: Mapped[dict[str, dict[str, int]]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class BillingCustomerModel(Base):
    """One payment-processor account per workspace, for its whole life.

    Survives cancellation on purpose: a returning customer reuses this
    record, so their saved payment methods and invoice history come back
    with them instead of starting empty.
    """

    __tablename__ = "billing_customers"
    __table_args__ = (
        CheckConstraint("provider IN ('stripe')", name="ck_billing_customers_provider"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Unique, not merely indexed: a workspace with two processor
    # identities would have its invoices split across two accounts, with
    # no way to tell which is authoritative.
    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(Text, default="stripe")
    # Also unique: two workspaces pointing at one processor customer
    # would let either one's admin read the other's invoices.
    provider_customer_id: Mapped[str] = mapped_column(Text, unique=True, index=True)
    # Where invoices go, when it differs from the workspace owner's login
    # address — finance teams rarely share a mailbox with engineers.
    billing_email: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class BillingSubscriptionModel(Base):
    """What a workspace is paying for, and where it is in its lifecycle."""

    __tablename__ = "billing_subscriptions"
    __table_args__ = (
        CheckConstraint(
            f"status IN {_SUBSCRIPTION_STATUSES}",
            name="ck_billing_subscriptions_status",
        ),
        CheckConstraint(
            "billing_interval IN ('monthly', 'annual')",
            name="ck_billing_subscriptions_interval",
        ),
        CheckConstraint(
            "current_period_end > current_period_start",
            name="ck_billing_subscriptions_period_ordered",
        ),
        # A `past_due` row with no clock is the indefinite-dunning bug
        # `billing-expert` warns about, made unrepresentable: without
        # `past_due_since` nothing can compute when the window closes, so
        # the subscription would sit unpaid and unserved-notice forever.
        CheckConstraint(
            "status <> 'past_due' OR past_due_since IS NOT NULL",
            name="ck_billing_subscriptions_past_due_has_clock",
        ),
        CheckConstraint(
            "status <> 'canceled' OR canceled_at IS NOT NULL",
            name="ck_billing_subscriptions_canceled_has_timestamp",
        ),
        # At most one live subscription per workspace. Partial rather than
        # a plain unique index because a workspace legitimately
        # accumulates canceled rows over time — that is its billing
        # history, and the constraint must not force us to delete it.
        Index(
            "uq_billing_subscriptions_one_live_per_workspace",
            "workspace_id",
            unique=True,
            postgresql_where="status <> 'canceled'",
        ),
        Index("ix_billing_subscriptions_workspace_status", "workspace_id", "status"),
        # Drives the dunning sweep: "every past_due subscription, oldest
        # failure first". Partial, because that job never looks at any
        # other status and the index has no reason to carry them.
        Index(
            "ix_billing_subscriptions_dunning",
            "past_due_since",
            postgresql_where="status = 'past_due'",
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    # RESTRICT, not CASCADE or SET NULL: deleting a plan that live
    # subscriptions reference must fail loudly. Cascading would delete
    # paying customers' subscriptions, and nulling would leave rows
    # nobody can price. Retiring a plan is `is_active = false`, which is
    # exactly why that column exists.
    plan_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("plans.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(Text, index=True)
    # `billing_interval`, not `interval` — INTERVAL is a reserved type
    # name in Postgres, and a column called that needs quoting in every
    # hand-written query forever.
    billing_interval: Mapped[str] = mapped_column(Text, default="monthly")
    current_period_start: Mapped[datetime] = mapped_column()
    current_period_end: Mapped[datetime] = mapped_column()
    trial_end: Mapped[datetime | None] = mapped_column(default=None)
    # A flag, not a status. See the note in domain/subscription.py: a
    # subscription scheduled to cancel is still active and still
    # entitled, because the customer has already paid for the period.
    cancel_at_period_end: Mapped[bool] = mapped_column(default=False)
    canceled_at: Mapped[datetime | None] = mapped_column(default=None)
    # When the *first* payment failed. The dunning clock runs from here
    # and is not reset by subsequent failures, so a repeatedly-failing
    # card cannot extend its own grace period indefinitely.
    past_due_since: Mapped[datetime | None] = mapped_column(default=None)
    provider_subscription_id: Mapped[str | None] = mapped_column(
        Text, unique=True, index=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class SubscriptionEventModel(Base):
    """Append-only log of every subscription state transition.

    Append-only in the same sense as `audit_logs` (CLAUDE.md §8): the
    application never issues UPDATE or DELETE against it. A subscription
    row shows the current state; this table is the only record of how it
    got there, which is what makes a disputed charge answerable months
    later.
    """

    __tablename__ = "subscription_events"
    __table_args__ = (
        CheckConstraint(
            f"from_status IN {_SUBSCRIPTION_STATUSES}",
            name="ck_subscription_events_from_status",
        ),
        CheckConstraint(
            f"to_status IN {_SUBSCRIPTION_STATUSES}",
            name="ck_subscription_events_to_status",
        ),
        Index("ix_subscription_events_workspace_time", "workspace_id", "occurred_at"),
        Index("ix_subscription_events_subscription_time", "subscription_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    subscription_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("billing_subscriptions.id", ondelete="CASCADE"),
        index=True,
    )
    # Denormalized from the subscription so every read of this table can
    # filter by tenant without a join (Rule 11: "every query carries and
    # filters by workspace_id").
    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    trigger: Mapped[str] = mapped_column(Text)
    from_status: Mapped[str] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text)
    # Who or what caused it: a user id, or `system:<job>` /
    # `provider:<name>` for machine-driven transitions. Free text rather
    # than an FK because the majority of transitions have no user behind
    # them at all, and a nullable FK plus a nullable label reads worse
    # than one always-populated string.
    actor: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    # The natural key that makes replay safe: a redelivered webhook or a
    # re-run job carries the same value, the unique index rejects the
    # second write, and the transition happens exactly once
    # (`billing-expert` operating principle 5).
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True, index=True)
    event_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())


class WebhookEventModel(Base):
    """Every payment-provider webhook this service has seen.

    The provider guarantees at-least-once delivery, not exactly-once, so
    the same event *will* arrive twice — during a retry after a timeout,
    or simply because the provider decided to. The unique index on
    `(provider, provider_event_id)` is what makes the second delivery a
    no-op, and it is a database constraint rather than an application
    check because the two deliveries can be in flight concurrently.

    Rows are written *before* the event is processed, in the same
    transaction as the state change it causes. A row that exists with
    `processed_at IS NULL` after a crash is a real finding — it means an
    event was received and its effect was rolled back — and the
    reconciliation job looks for exactly that.
    """

    __tablename__ = "billing_webhook_events"
    __table_args__ = (
        CheckConstraint("provider IN ('stripe')", name="ck_billing_webhook_events_provider"),
        CheckConstraint(
            "status IN ('received', 'processed', 'ignored', 'failed')",
            name="ck_billing_webhook_events_status",
        ),
        Index(
            "uq_billing_webhook_events_provider_event",
            "provider",
            "provider_event_id",
            unique=True,
        ),
        # The stuck-event sweep: anything received and not yet resolved,
        # oldest first. Partial, because that query never looks at the
        # resolved majority.
        Index(
            "ix_billing_webhook_events_unresolved",
            "received_at",
            postgresql_where="status = 'received'",
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    provider: Mapped[str] = mapped_column(Text, default="stripe")
    provider_event_id: Mapped[str] = mapped_column(Text, index=True)
    event_type: Mapped[str] = mapped_column(Text)
    # Nullable: an event can arrive that this service cannot attribute to
    # a workspace (a customer created outside the product, say). Recorded
    # anyway — an unattributable event is worth seeing, and discarding it
    # would hide it.
    workspace_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        default=None,
        index=True,
    )
    status: Mapped[str] = mapped_column(Text, default="received")
    error: Mapped[str | None] = mapped_column(Text, default=None)
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(default=None)


class UsageEventModel(Base):
    """Durable, append-only metered usage. The billing source of truth.

    Partitioned by `occurred_at` (RANGE, monthly) from its first
    migration rather than retrofitted — CLAUDE.md §8 names this table
    specifically, and a billing table is the worst possible candidate for
    a partitioning migration under production pain, because the fix
    window is exactly when the rows cannot be moved.

    The composite primary key is a Postgres requirement (the partition
    key must appear in every unique key on a partitioned table), not a
    modelling choice — same shape as `agent_run_steps`.

    Redis is never the source here (Rule 13). A cached counter may drive
    a progress bar; the invoice reads these rows.
    """

    __tablename__ = "billing_usage_events"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_billing_usage_events_quantity"),
        CheckConstraint(
            "cost_micro_usd IS NULL OR cost_micro_usd >= 0",
            name="ck_billing_usage_events_cost",
        ),
        # Primary access pattern: "everything this workspace used in this
        # billing period, by dimension" — the aggregation job's only
        # query, and the one behind the live usage panel. Leads with
        # `workspace_id` per Rule 11 and §8.
        Index(
            "ix_billing_usage_events_workspace_period",
            "workspace_id",
            "occurred_at",
            "dimension",
        ),
        # The replay guard. Includes `occurred_at` because Postgres
        # requires the partition key in every unique index on a
        # partitioned table; the key itself is derived from the source
        # row, so a retried worker reproduces both halves.
        Index(
            "uq_billing_usage_events_idempotency",
            "idempotency_key",
            "occurred_at",
            unique=True,
        ),
        {"postgresql_partition_by": "RANGE (occurred_at)"},
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    occurred_at: Mapped[datetime] = mapped_column(primary_key=True)
    # No FK to `workspaces`: Postgres cannot enforce a foreign key from a
    # partitioned table cheaply, and more importantly a billing record
    # must survive its workspace being deleted — an invoice for a closed
    # account still has to be explicable. Tenant scoping is enforced by
    # every query carrying `workspace_id`, per Rule 11.
    workspace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True)
    dimension: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    # The row that produced this event (a run id, a tool-call id). Kept so
    # an unexpected invoice line can be traced to the work that caused it.
    source_id: Mapped[str | None] = mapped_column(Text, default=None)
    quantity: Mapped[int] = mapped_column(BigInteger)
    # Micro-USD (1e-6 USD), not cents: a single LLM call routinely costs a
    # fraction of a cent, and rounding per call would round most to zero.
    # Converted to cents exactly once, at the invoice boundary.
    cost_micro_usd: Mapped[int | None] = mapped_column(BigInteger, default=None)
    idempotency_key: Mapped[str] = mapped_column(Text)
    event_metadata: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)


class UsageRollupModel(Base):
    """A billing period's finalized totals, one row per dimension.

    Separate from the events on purpose. `billing-expert` requires usage
    aggregation and invoice generation to be distinct, individually
    testable steps: this table is the boundary between them. Invoicing
    reads finalized rollups and never scans the event partitions, so an
    invoice cannot change because a late event arrived after it was
    issued.

    Keyed by `(workspace_id, period_start, dimension)` so the aggregation
    job is idempotent — re-running it recomputes the same row rather than
    adding a second.
    """

    __tablename__ = "billing_usage_rollups"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_billing_usage_rollups_quantity"),
        CheckConstraint("cost_micro_usd >= 0", name="ck_billing_usage_rollups_cost"),
        CheckConstraint(
            "period_end > period_start", name="ck_billing_usage_rollups_period_ordered"
        ),
        Index(
            "uq_billing_usage_rollups_key",
            "workspace_id",
            "period_start",
            "dimension",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), index=True)
    period_start: Mapped[datetime] = mapped_column()
    period_end: Mapped[datetime] = mapped_column()
    dimension: Mapped[str] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(BigInteger, default=0)
    cost_micro_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    # Set when the period closes and the totals stop moving. A rollup
    # with `finalized_at` set is safe to invoice; one without is a live
    # running total, and invoicing it would bill a period still in
    # progress.
    finalized_at: Mapped[datetime | None] = mapped_column(default=None)
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())
