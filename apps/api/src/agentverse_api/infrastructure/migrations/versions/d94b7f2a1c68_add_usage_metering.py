"""add usage events (partitioned) and period rollups

Revision ID: d94b7f2a1c68
Revises: a3f81c6e5d72
Create Date: 2026-08-05

Two tables that are deliberately not one.

`billing_usage_events` is the append-only record of what happened —
partitioned by `occurred_at` (RANGE, monthly) from this first migration
rather than retrofitted. CLAUDE.md §8 names this table specifically, and
a billing table is the worst candidate for a partitioning migration
under production pain: the window when the fix is needed is exactly the
window when the rows cannot be moved. The composite primary key
`(id, occurred_at)` is a Postgres requirement — the partition key must
appear in every unique key on a partitioned table — not a modelling
choice. Same shape as `agent_run_steps` (`4387a581c5e4`).

`billing_usage_rollups` is a period's finalized totals. Keeping them
separate is what makes aggregation and invoicing two individually
testable steps: invoicing reads finalized rollups and never scans the
event partitions, so an issued invoice cannot change because a late
event arrived afterwards.

Partitions: twelve monthly partitions from the current month, plus a
DEFAULT catch-all. The catch-all is the important part — without it, an
insert for a month nobody pre-created would be *rejected*, and a billing
record that fails to insert is revenue nobody can reconstruct. Rows
landing in DEFAULT are a signal to run the maintenance job, not a
failure.

`workspace_id` has no foreign key here, deliberately. Postgres cannot
enforce a foreign key from a partitioned table cheaply, and a billing
record must outlive its workspace — an invoice for a closed account
still has to be explicable. Tenant scoping is enforced by every query
carrying `workspace_id` (Rule 11).

Additive and reversible. Code at the previous revision writes no usage
events, so a rollback loses nothing it was recording.
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d94b7f2a1c68"
down_revision = "a3f81c6e5d72"
branch_labels = None
depends_on = None

#: How many monthly partitions to pre-create. A year of headroom means
#: the maintenance job can be late by months without a single row
#: falling to DEFAULT — and if it does, DEFAULT catches it rather than
#: rejecting the write.
_MONTHS_AHEAD = 12


def _year_month(base_year: int, month_index: int) -> tuple[int, int]:
    """Normalise a 0-based month offset into `(year, month)`."""
    return base_year + month_index // 12, month_index % 12 + 1


def _month_bounds(offset: int) -> tuple[str, str, str]:
    """`(suffix, from, to)` for the partition `offset` months after the
    start of the current month. Computed in Python rather than SQL so the
    generated DDL is visible in the migration's own log output.
    """
    now = datetime.now(UTC)
    index = now.month - 1 + offset
    year, month = _year_month(now.year, index)
    next_year, next_month = _year_month(now.year, index + 1)
    return (
        f"{year:04d}_{month:02d}",
        f"{year:04d}-{month:02d}-01",
        f"{next_year:04d}-{next_month:02d}-01",
    )


def upgrade() -> None:
    op.create_table(
        "billing_usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("dimension", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=True),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        # Micro-USD, not cents: a single LLM call routinely costs a
        # fraction of a cent. Converted to cents once, at the invoice
        # boundary.
        sa.Column("cost_micro_usd", sa.BigInteger(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.CheckConstraint("quantity >= 0", name="ck_billing_usage_events_quantity"),
        sa.CheckConstraint(
            "cost_micro_usd IS NULL OR cost_micro_usd >= 0",
            name="ck_billing_usage_events_cost",
        ),
        sa.PrimaryKeyConstraint("id", "occurred_at"),
        postgresql_partition_by="RANGE (occurred_at)",
    )
    op.create_index(
        "ix_billing_usage_events_workspace_id", "billing_usage_events", ["workspace_id"]
    )
    # Primary access pattern: "everything this workspace used in this
    # billing period, by dimension" — the aggregation job's only query
    # and the one behind the live usage panel. Leads with `workspace_id`
    # per Rule 11.
    op.create_index(
        "ix_billing_usage_events_workspace_period",
        "billing_usage_events",
        ["workspace_id", "occurred_at", "dimension"],
    )
    # The replay guard: a worker that crashes after recording and before
    # acknowledging re-runs and re-records. `occurred_at` is included
    # because Postgres requires the partition key in every unique index
    # on a partitioned table; the key itself is derived from the source
    # row, so a retry reproduces both halves.
    op.create_index(
        "uq_billing_usage_events_idempotency",
        "billing_usage_events",
        ["idempotency_key", "occurred_at"],
        unique=True,
    )

    for offset in range(_MONTHS_AHEAD):
        suffix, lower, upper = _month_bounds(offset)
        op.execute(
            f"CREATE TABLE billing_usage_events_{suffix} "
            f"PARTITION OF billing_usage_events "
            f"FOR VALUES FROM ('{lower}') TO ('{upper}')"
        )
    # The catch-all. Without it an insert for an un-provisioned month is
    # rejected outright, and a billing record that fails to insert is
    # revenue nobody can reconstruct. Rows here mean "run the maintenance
    # job", not "something broke".
    op.execute(
        "CREATE TABLE billing_usage_events_default PARTITION OF billing_usage_events DEFAULT"
    )

    op.create_table(
        "billing_usage_rollups",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dimension", sa.Text(), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cost_micro_usd", sa.BigInteger(), nullable=False, server_default="0"),
        # Set when the period closes. A rollup without it is a live
        # running total, and invoicing one would bill a period still in
        # progress.
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("quantity >= 0", name="ck_billing_usage_rollups_quantity"),
        sa.CheckConstraint("cost_micro_usd >= 0", name="ck_billing_usage_rollups_cost"),
        sa.CheckConstraint(
            "period_end > period_start", name="ck_billing_usage_rollups_period_ordered"
        ),
    )
    op.create_index(
        "ix_billing_usage_rollups_workspace_id", "billing_usage_rollups", ["workspace_id"]
    )
    # Makes the aggregation job idempotent: a re-run updates this row
    # rather than adding a second total for the same period.
    op.create_index(
        "uq_billing_usage_rollups_key",
        "billing_usage_rollups",
        ["workspace_id", "period_start", "dimension"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("billing_usage_rollups")
    # Dropping the parent drops every partition with it; the explicit
    # DEFAULT drop first is belt-and-braces for a partially-applied
    # upgrade.
    op.execute("DROP TABLE IF EXISTS billing_usage_events_default")
    op.drop_table("billing_usage_events")
