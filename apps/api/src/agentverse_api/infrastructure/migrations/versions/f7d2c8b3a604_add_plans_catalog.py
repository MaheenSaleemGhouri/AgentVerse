"""add plans catalog and seed the four tiers

Revision ID: f7d2c8b3a604
Revises: e8c1a4f70d23
Create Date: 2026-08-03

Creates `plans` — the single row set that both the pricing page and
server-side entitlement enforcement read. Keeping the catalog in
Postgres rather than a Python constant is what makes the plans
configurable from the backend: changing a limit or a price is an UPDATE,
not a deploy.

The seed rows are part of the migration rather than a separate script
because the catalog is not optional data. A workspace with no
subscription is on Free by definition, so `EntitlementService` resolves
the Free row on every request; an empty `plans` table is a broken
install, not an empty one, and the code raises `CatalogIncompleteError`
rather than falling back to limits hardcoded somewhere else.

Enum-like columns are TEXT + CHECK, never a Postgres ENUM — same
reversibility reasoning as the role columns in `b3f7c1a9e582`
(`ALTER TYPE ... DROP VALUE` does not exist, and Rule 19 requires a
working `downgrade()`).

Additive and reversible. The downgrade drops the table, which loses any
operator edits to prices or limits — acceptable in the rollback
direction because code at the previous revision never read it, and no
other table references it yet (subscriptions arrive in a later
migration, and that one carries the FK).
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f7d2c8b3a604"
down_revision = "e8c1a4f70d23"
branch_labels = None
depends_on = None


# Overage is priced per increment, not per unit: "$3.00 per 1,000 agent
# runs" is expressible in integer cents (Rule 15) and "$0.003 per run" is
# not. Free carries no overage rates at all — a free workspace is
# refused at its limit rather than billed, which is the only way to
# guarantee a free user is never surprised by an invoice.
_PRO_OVERAGE: dict[str, dict[str, int]] = {
    "agent_runs": {"billing_increment": 1_000, "price_cents_per_increment": 300},
    "tokens": {"billing_increment": 1_000_000, "price_cents_per_increment": 200},
    "mcp_calls": {"billing_increment": 1_000, "price_cents_per_increment": 100},
    "workflow_executions": {"billing_increment": 1_000, "price_cents_per_increment": 300},
    "background_jobs": {"billing_increment": 1_000, "price_cents_per_increment": 100},
    "api_calls": {"billing_increment": 10_000, "price_cents_per_increment": 50},
    "bandwidth_mb": {"billing_increment": 1_000, "price_cents_per_increment": 10},
    "knowledge_storage_mb": {"billing_increment": 1_000, "price_cents_per_increment": 25},
    "vector_storage_mb": {"billing_increment": 1_000, "price_cents_per_increment": 50},
}

# Team buys volume, so its per-increment rates are lower than Pro's.
# Without that, a workspace could pay more per unit after upgrading,
# which makes the upgrade a worse deal at exactly the usage level that
# triggers it.
_TEAM_OVERAGE: dict[str, dict[str, int]] = {
    "agent_runs": {"billing_increment": 1_000, "price_cents_per_increment": 200},
    "tokens": {"billing_increment": 1_000_000, "price_cents_per_increment": 150},
    "mcp_calls": {"billing_increment": 1_000, "price_cents_per_increment": 75},
    "workflow_executions": {"billing_increment": 1_000, "price_cents_per_increment": 200},
    "background_jobs": {"billing_increment": 1_000, "price_cents_per_increment": 75},
    "api_calls": {"billing_increment": 10_000, "price_cents_per_increment": 35},
    "bandwidth_mb": {"billing_increment": 1_000, "price_cents_per_increment": 8},
    "knowledge_storage_mb": {"billing_increment": 1_000, "price_cents_per_increment": 20},
    "vector_storage_mb": {"billing_increment": 1_000, "price_cents_per_increment": 40},
}


def _seed_rows() -> list[dict[str, object]]:
    """The four tiers. `None` on any limit means unlimited.

    Prices are integer cents. Annual is priced at ten months, so the
    annual toggle saves a real, statable 16% rather than a rounded claim.
    """
    return [
        {
            "id": str(uuid.uuid4()),
            "slug": "free",
            "display_name": "Free",
            "description": "For individual builders getting started.",
            "monthly_price_cents": 0,
            "annual_price_cents": 0,
            "currency": "usd",
            "trial_days": 0,
            "is_public": True,
            "is_active": True,
            "sort_order": 0,
            "resource_limits": {
                "agents": 3,
                "teams": 0,
                "knowledge_bases": 1,
                "mcp_connections": 1,
                "seats": 1,
                "concurrent_runs": 1,
            },
            "metered_allowances": {
                "agent_runs": 500,
                "tokens": 100_000,
                "mcp_calls": 500,
                "workflow_executions": 0,
                "background_jobs": 500,
                "api_calls": 5_000,
                "bandwidth_mb": 1_000,
                "knowledge_storage_mb": 100,
                "vector_storage_mb": 100,
            },
            "capabilities": ["community_support"],
            "overage_rates": {},
        },
        {
            "id": str(uuid.uuid4()),
            "slug": "pro",
            "display_name": "Pro",
            "description": "For builders shipping agents to production.",
            "monthly_price_cents": 2_900,
            "annual_price_cents": 29_000,
            "currency": "usd",
            "trial_days": 14,
            "is_public": True,
            "is_active": True,
            "sort_order": 1,
            "resource_limits": {
                "agents": 25,
                "teams": 5,
                "knowledge_bases": 10,
                "mcp_connections": 10,
                "seats": 3,
                "concurrent_runs": 5,
            },
            "metered_allowances": {
                "agent_runs": 10_000,
                "tokens": 5_000_000,
                "mcp_calls": 25_000,
                "workflow_executions": 2_000,
                "background_jobs": 10_000,
                "api_calls": 250_000,
                "bandwidth_mb": 50_000,
                "knowledge_storage_mb": 5_000,
                "vector_storage_mb": 5_000,
            },
            "capabilities": ["multi_agent", "priority_queue", "analytics"],
            "overage_rates": _PRO_OVERAGE,
        },
        {
            "id": str(uuid.uuid4()),
            "slug": "team",
            "display_name": "Team",
            "description": "For teams collaborating on agents, with SSO and audit logs.",
            "monthly_price_cents": 9_900,
            "annual_price_cents": 99_000,
            "currency": "usd",
            "trial_days": 14,
            "is_public": True,
            "is_active": True,
            "sort_order": 2,
            "resource_limits": {
                "agents": None,
                "teams": None,
                "knowledge_bases": None,
                "mcp_connections": None,
                "seats": 25,
                "concurrent_runs": 25,
            },
            "metered_allowances": {
                "agent_runs": 100_000,
                "tokens": 50_000_000,
                "mcp_calls": 250_000,
                "workflow_executions": 25_000,
                "background_jobs": 100_000,
                "api_calls": 2_500_000,
                "bandwidth_mb": 500_000,
                "knowledge_storage_mb": 50_000,
                "vector_storage_mb": 50_000,
            },
            "capabilities": [
                "multi_agent",
                "priority_queue",
                "analytics",
                "team_collaboration",
                "sso",
                "scim",
                "audit_log_export",
                "custom_roles",
                "ip_allowlist",
                "priority_support",
            ],
            "overage_rates": _TEAM_OVERAGE,
        },
        {
            "id": str(uuid.uuid4()),
            "slug": "enterprise",
            "display_name": "Enterprise",
            "description": (
                "For organisations needing dedicated infrastructure, an SLA and white labelling."
            ),
            # NULL, not 0: Enterprise is quoted, not published. Zero
            # would render as "free" on the pricing page.
            "monthly_price_cents": None,
            "annual_price_cents": None,
            "currency": "usd",
            "trial_days": 0,
            "is_public": True,
            "is_active": True,
            "sort_order": 3,
            "resource_limits": {
                "agents": None,
                "teams": None,
                "knowledge_bases": None,
                "mcp_connections": None,
                "seats": None,
                "concurrent_runs": None,
            },
            "metered_allowances": {
                "agent_runs": None,
                "tokens": None,
                "mcp_calls": None,
                "workflow_executions": None,
                "background_jobs": None,
                "api_calls": None,
                "bandwidth_mb": None,
                "knowledge_storage_mb": None,
                "vector_storage_mb": None,
            },
            "capabilities": [
                "multi_agent",
                "priority_queue",
                "analytics",
                "team_collaboration",
                "sso",
                "scim",
                "audit_log_export",
                "custom_roles",
                "ip_allowlist",
                "priority_support",
                "dedicated_support",
                "dedicated_infrastructure",
                "sla",
                "white_label",
                "custom_integrations",
            ],
            # No overage rates: every allowance is unlimited, so there is
            # nothing to exceed. An empty map states that; rates that can
            # never apply would be dead configuration.
            "overage_rates": {},
        },
    ]


def upgrade() -> None:
    plans = op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("monthly_price_cents", sa.Integer(), nullable=True),
        sa.Column("annual_price_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=False, server_default="usd"),
        sa.Column("trial_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "resource_limits",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "metered_allowances",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "capabilities",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "overage_rates",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "slug IN ('free', 'pro', 'team', 'enterprise')",
            name="ck_plans_slug",
        ),
        sa.CheckConstraint(
            "monthly_price_cents IS NULL OR monthly_price_cents >= 0",
            name="ck_plans_monthly_price_non_negative",
        ),
        sa.CheckConstraint(
            "annual_price_cents IS NULL OR annual_price_cents >= 0",
            name="ck_plans_annual_price_non_negative",
        ),
        sa.CheckConstraint("trial_days >= 0", name="ck_plans_trial_days_non_negative"),
    )
    # Unique rather than merely indexed: a tier resolves to exactly one
    # catalog row, and two rows for `pro` would make "which plan is this
    # workspace on" ambiguous at the worst possible moment.
    op.create_index("ix_plans_slug", "plans", ["slug"], unique=True)

    op.bulk_insert(plans, _seed_rows())


def downgrade() -> None:
    op.drop_index("ix_plans_slug", table_name="plans")
    op.drop_table("plans")
