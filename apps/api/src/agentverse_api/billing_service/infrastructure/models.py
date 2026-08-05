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

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, TypeDecorator
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
