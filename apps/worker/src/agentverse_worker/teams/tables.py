"""SQLAlchemy Core mirrors of apps/api's Phase 9 team schema.

Same "shared wire contract, not shared code" pattern as
`agentverse_worker/agents/tables.py`: apps/api's Alembic migrations
(`a91f4c37bd08`, `b3d70e2c1a45`) are the one source of truth for the
schema; this worker declares only the columns it reads and writes, via
Core rather than apps/api's declarative ORM classes — importing those
would pull a FastAPI-adjacent dependency tree into the worker for no
benefit and couple two independently deployable services at the source
level (CLAUDE.md §5).
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    Table,
    Text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()

team_topology_enum = postgresql.ENUM(
    "supervisor_worker",
    "planner_executor_critic",
    "sequential",
    "parallel",
    name="team_topology",
    create_type=False,
)
team_member_role_enum = postgresql.ENUM(
    "supervisor",
    "planner",
    "executor",
    "critic",
    "researcher",
    "coder",
    "writer",
    "worker",
    "aggregator",
    name="team_member_role",
    create_type=False,
)
team_session_status_enum = postgresql.ENUM(
    "queued",
    "running",
    "success",
    "error",
    "cancelled",
    name="team_session_status",
    create_type=False,
)
handoff_kind_enum = postgresql.ENUM(
    "automatic", "manual", "conditional", "parallel", name="handoff_kind", create_type=False
)
memory_scope_enum = postgresql.ENUM(
    "team", "session", "agent", name="memory_scope", create_type=False
)
communication_kind_enum = postgresql.ENUM(
    "task_request",
    "task_result",
    "context_share",
    "intermediate_result",
    "error_report",
    name="communication_kind",
    create_type=False,
)

# Only the two columns the team runtime reads: a member points at an
# agent, and the agent points at the version it publishes. Everything
# else about an agent is apps/api's concern.
agents_table = Table(
    "agents",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("published_version_id", UUID(as_uuid=False)),
)

teams_table = Table(
    "teams",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("name", Text),
    Column("description", Text),
    Column("topology", team_topology_enum),
    Column("objective", Text),
    Column("max_turns", Integer),
    Column("max_cost_micro_usd", BigInteger),
    Column("timeout_seconds", Integer),
    Column("shared_memory_enabled", Boolean),
    Column("shared_knowledge_base_ids", JSONB),
    Column("deleted_at", DateTime(timezone=True)),
)

team_members_table = Table(
    "team_members",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("team_id", UUID(as_uuid=False)),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("agent_id", UUID(as_uuid=False)),
    Column("role", team_member_role_enum),
    Column("position", Integer),
    Column("handoff_description", Text),
    Column("can_receive_handoff", Boolean),
)

team_sessions_table = Table(
    "team_sessions",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("team_id", UUID(as_uuid=False)),
    Column("status", team_session_status_enum),
    Column("input", JSONB),
    Column("output", Text),
    Column("error_message", Text),
    Column("cost_micro_usd", BigInteger),
    Column("total_turns", Integer),
    Column("idempotency_key", Text),
    Column("started_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True)),
)

handoffs_table = Table(
    "handoffs",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("session_id", UUID(as_uuid=False)),
    Column("from_agent_id", UUID(as_uuid=False)),
    Column("to_agent_id", UUID(as_uuid=False)),
    Column("kind", handoff_kind_enum),
    Column("contract", JSONB),
    Column("reason", Text),
    Column("sequence", Integer),
    Column("created_at", DateTime(timezone=True)),
)

shared_memory_table = Table(
    "shared_memory",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("team_id", UUID(as_uuid=False)),
    Column("session_id", UUID(as_uuid=False)),
    Column("agent_id", UUID(as_uuid=False)),
    Column("scope", memory_scope_enum),
    Column("key", Text),
    Column("value", JSONB),
    Column("created_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
)

communication_logs_table = Table(
    "communication_logs",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("session_id", UUID(as_uuid=False)),
    Column("from_agent_id", UUID(as_uuid=False)),
    Column("to_agent_id", UUID(as_uuid=False)),
    Column("kind", communication_kind_enum),
    Column("content", JSONB),
    Column("sequence", Integer),
    Column("created_at", DateTime(timezone=True)),
)

execution_events_table = Table(
    "execution_events",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("created_at", DateTime(timezone=True), primary_key=True),
    Column("session_id", UUID(as_uuid=False)),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("event_type", Text),
    Column("agent_id", UUID(as_uuid=False)),
    Column("sequence", Integer),
    Column("payload", JSONB),
    Column("cost_micro_usd", BigInteger),
)

team_session_items_table = Table(
    "team_session_items",
    metadata,
    # `id` is a Postgres identity column — never supplied on insert, and
    # relied on for ordering (see migration b3d70e2c1a45).
    # `autoincrement=True` is required explicitly on a composite primary
    # key: SQLAlchemy otherwise assumes the column needs a client-supplied
    # value and warns on every insert.
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("created_at", DateTime(timezone=True), primary_key=True),
    Column("session_id", UUID(as_uuid=False)),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("agent_id", UUID(as_uuid=False)),
    Column("item", JSONB),
)
