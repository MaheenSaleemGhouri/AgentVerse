"""SQLAlchemy Core mirrors of the tables the retention sweep reads and
deletes from.

Same "shared wire contract, not shared code" pattern as
`mcp/tables.py`: apps/api's Alembic migrations are the one source of
truth, and this worker declares only the columns it touches.

`agent_run_steps`, `execution_events` and `tool_calls` are deliberately
absent: every one of them is `ON DELETE CASCADE` from `agent_runs`, so
deleting the run removes them in the same statement. Declaring them here
would invite a second, redundant delete pass that could only ever
diverge from the FK behaviour.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, MetaData, Table, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()

agent_runs_table = Table(
    "agent_runs",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

workspace_settings_table = Table(
    "workspace_settings",
    metadata,
    Column("workspace_id", UUID(as_uuid=False), primary_key=True),
    Column("retention_days", Integer, nullable=True),
)

#: The purge is a destructive, system-initiated action, so it records
#: itself (CLAUDE.md §10). Only ever INSERTed here — `audit_logs` is
#: append-only, and the sweep never purges it: retention deletes run
#: history, not the record that the deletion happened.
audit_logs_table = Table(
    "audit_logs",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False), nullable=True),
    Column("actor_user_id", Text, nullable=True),
    Column("action", Text, nullable=False),
    Column("target", Text, nullable=True),
    Column("outcome", Text, nullable=False),
    Column("metadata", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
