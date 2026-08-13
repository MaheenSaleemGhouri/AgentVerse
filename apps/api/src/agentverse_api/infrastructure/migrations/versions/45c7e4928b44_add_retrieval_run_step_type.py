"""add 'retrieval' to the run_step_type enum

Revision ID: 45c7e4928b44
Revises: b6e2f04a9d17
Create Date: 2026-08-13

`RunStepType` (domain/run_entities.py) and the frontend's `RunStepType`
union (apps/web/lib/hooks/useAgentRunStream.ts) have both carried a
`"retrieval"` member since the RAG pipeline shipped in Phase 5 — but the
Postgres enum `run_step_type`, created in `4387a581c5e4` with only five
values, was never grown to match. Every run against a knowledge-base
agent failed the moment retrieval actually found a chunk and the worker
tried to record a `retrieval` step:
`InvalidTextRepresentationError: invalid input value for enum
run_step_type: "retrieval"`. This is additive-only, so it never
regressed anything visibly — RAG retrieval just could never complete
until today's KB-upload fix (`5d968ec`) let a chunk exist to retrieve.

Not converted to TEXT + CHECK (this repo's usual preference over
Postgres ENUM, per `f7d2c8b3a604`'s docstring) because `agent_run_steps`
is range-partitioned and already has five in-use rows on the old type;
that conversion is a real migration project, not a one-value hotfix.

`downgrade()` is a documented no-op: Postgres has `ALTER TYPE ... ADD
VALUE` but no `DROP VALUE` — removing an enum value requires rebuilding
the type from scratch (create a new type, cast every column, swap
names, drop the old one), which is far riskier than leaving an unused
label behind. `run_step_type` was already in this position before this
migration (nothing here has ever been able to downgrade all the way to
"no enum type"); this migration does not make that pre-existing
constraint worse, and rolling back the *code* only stops writing the
value; it does not need the label gone.
"""

from __future__ import annotations

from alembic import op

revision = "45c7e4928b44"
down_revision = "b6e2f04a9d17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Must run outside the migration's transaction: Postgres forbids
    # using a value added by `ALTER TYPE ... ADD VALUE` within the same
    # transaction that added it, and some drivers additionally refuse to
    # run the ALTER itself inside an existing transaction block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE run_step_type ADD VALUE IF NOT EXISTS 'retrieval'")


def downgrade() -> None:
    # No-op — see the module docstring. Postgres cannot drop a single
    # enum value without rebuilding the type.
    pass
