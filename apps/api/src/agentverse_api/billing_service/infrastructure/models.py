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

from sqlalchemy import CheckConstraint, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from agentverse_api.billing_service.domain.plan import PlanTier
from agentverse_api.infrastructure.orm_base import Base


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
