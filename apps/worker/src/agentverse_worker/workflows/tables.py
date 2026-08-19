"""SQLAlchemy Core table definitions mirroring apps/api's authoritative
workflow schema (`apps/api/.../orchestration_service/infrastructure/
models.py`, migration `0958619d3576`) — same "shared wire contract, not
shared code" pattern as `agents/tables.py`/`teams/tables.py`.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()

workflow_nodes_table = Table(
    "workflow_nodes",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workflow_version_id", UUID(as_uuid=False)),
    Column("type", Text),
    Column("position_x", Float),
    Column("position_y", Float),
    Column("config", JSONB),
    Column("agent_id", UUID(as_uuid=False)),
    Column("team_id", UUID(as_uuid=False)),
)

workflow_edges_table = Table(
    "workflow_edges",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workflow_version_id", UUID(as_uuid=False)),
    Column("from_node_id", UUID(as_uuid=False)),
    Column("to_node_id", UUID(as_uuid=False)),
    Column("condition", JSONB),
    Column("branch_order", Integer),
)

workflow_runs_table = Table(
    "workflow_runs",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("workflow_id", UUID(as_uuid=False)),
    Column("workflow_version_id", UUID(as_uuid=False)),
    Column("status", Text),
    Column("input", JSONB),
    Column("idempotency_key", Text),
    Column("cost_micro_usd", BigInteger),
    Column("error_message", Text),
    Column("started_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True)),
)

workflow_node_runs_table = Table(
    "workflow_node_runs",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("created_at", DateTime(timezone=True), primary_key=True),
    Column("workflow_run_id", UUID(as_uuid=False), ForeignKey("workflow_runs.id")),
    Column("node_id", UUID(as_uuid=False)),
    Column("agent_run_id", UUID(as_uuid=False)),
    Column("team_session_id", UUID(as_uuid=False)),
    Column("status", Text),
    Column("output", JSONB),
    Column("approval_decision", Text),
    Column("approved_by_user_id", Text),
    Column("approved_at", DateTime(timezone=True)),
    Column("sequence", Integer),
    Column("started_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
)
