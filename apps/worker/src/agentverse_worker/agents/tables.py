"""SQLAlchemy Core table definitions mirroring apps/api's authoritative
schema for `agent_versions`/`agent_runs`/`agent_run_steps`
(`apps/api/src/agentverse_api/orchestration_service/infrastructure/models.py`,
migration `4387a581c5e4`).

This is the same "shared wire contract, not shared code" pattern Phase 3
chose for the job queue: apps/api's Alembic migrations are the one
source of truth for the schema itself; this worker only needs to
read/write a handful of columns and does so via plain SQLAlchemy Core
(not the declarative ORM classes, which are apps/api-owned and would
pull FastAPI-adjacent dependencies into this service for no reason).
If the schema changes, both sides update in lockstep against the
migration, not against each other's source.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, MetaData, Table, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()

run_status_enum = postgresql.ENUM(
    "queued", "running", "success", "error", "cancelled", name="run_status", create_type=False
)
run_step_type_enum = postgresql.ENUM(
    "run_started",
    "llm_call",
    "tool_call",
    "run_completed",
    "run_failed",
    name="run_step_type",
    create_type=False,
)

agent_versions_table = Table(
    "agent_versions",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("agent_id", UUID(as_uuid=False), ForeignKey("agents.id")),
    Column("version_number", Integer),
    Column("config", JSONB),
    Column("created_by_user_id", Text),
    Column("created_at", DateTime(timezone=True)),
)

agent_runs_table = Table(
    "agent_runs",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("agent_id", UUID(as_uuid=False)),
    Column("agent_version_id", UUID(as_uuid=False)),
    Column("status", run_status_enum),
    Column("input", JSONB),
    Column("idempotency_key", Text),
    Column("cost_micro_usd", BigInteger),
    Column("error_message", Text),
    Column("started_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True)),
)

agent_run_steps_table = Table(
    "agent_run_steps",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("created_at", DateTime(timezone=True), primary_key=True),
    Column("run_id", UUID(as_uuid=False), ForeignKey("agent_runs.id")),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("step_type", run_step_type_enum),
    Column("sequence", Integer),
    Column("payload", JSONB),
    Column("cost_micro_usd", BigInteger),
)
