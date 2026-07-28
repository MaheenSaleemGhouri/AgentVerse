"""SQLAlchemy Core mirrors of apps/api's Phase 6 integration schema.

Same "shared wire contract, not shared code" pattern as
`agents/tables.py` and `teams/tables.py`: apps/api's Alembic migration
(`c4e81f3d9b27`) is the one source of truth; this worker declares only
the columns it reads.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    LargeBinary,
    MetaData,
    Table,
    Text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()

mcp_transport_enum = postgresql.ENUM(
    "stdio", "sse", "streamable_http", name="mcp_transport", create_type=False
)
mcp_auth_scheme_enum = postgresql.ENUM(
    "none",
    "api_key",
    "bearer_token",
    "basic",
    "oauth2",
    "jwt",
    "custom_header",
    name="mcp_auth_scheme",
    create_type=False,
)
mcp_install_status_enum = postgresql.ENUM(
    "pending_auth", "active", "disabled", "error", name="mcp_install_status", create_type=False
)
mcp_health_status_enum = postgresql.ENUM(
    "healthy", "degraded", "unreachable", "unknown", name="mcp_health_status", create_type=False
)
mcp_permission_level_enum = postgresql.ENUM(
    "read_only", "read_write", "admin", name="mcp_permission_level", create_type=False
)
tool_call_status_enum = postgresql.ENUM(
    "success",
    "error",
    "timeout",
    "denied",
    "circuit_open",
    "cached",
    name="tool_call_status",
    create_type=False,
)

mcp_servers_table = Table(
    "mcp_servers",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("slug", Text),
    Column("name", Text),
    Column("transport", mcp_transport_enum),
    Column("auth_scheme", mcp_auth_scheme_enum),
    Column("command", Text),
    Column("command_args", JSONB),
    Column("endpoint_url", Text),
    Column("required_credentials", JSONB),
)

installed_servers_table = Table(
    "installed_servers",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("mcp_server_id", UUID(as_uuid=False)),
    Column("display_name", Text),
    Column("transport", mcp_transport_enum),
    Column("endpoint_url", Text),
    Column("status", mcp_install_status_enum),
    Column("health", mcp_health_status_enum),
    Column("config", JSONB),
    Column("discovered_tools", JSONB),
    Column("tools_discovered_at", DateTime(timezone=True)),
    Column("last_health_check_at", DateTime(timezone=True)),
    Column("last_error", Text),
    Column("deleted_at", DateTime(timezone=True)),
)

credentials_table = Table(
    "credentials",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("installed_server_id", UUID(as_uuid=False)),
    Column("key", Text),
    Column("auth_scheme", mcp_auth_scheme_enum),
    Column("ciphertext", LargeBinary),
    Column("wrapped_dek", LargeBinary),
    Column("key_version", Text),
    Column("expires_at", DateTime(timezone=True)),
)

permissions_table = Table(
    "permissions",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("installed_server_id", UUID(as_uuid=False)),
    Column("agent_id", UUID(as_uuid=False)),
    Column("team_id", UUID(as_uuid=False)),
    Column("level", mcp_permission_level_enum),
    Column("allowed_tools", JSONB),
    Column("timeout_seconds", Integer),
    Column("max_retries", Integer),
    Column("cache_ttl_seconds", Integer),
    Column("max_calls_per_run", Integer),
    Column("priority", Integer),
)

workspace_integrations_table = Table(
    "workspace_integrations",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("installed_server_id", UUID(as_uuid=False)),
    Column("is_enabled", Boolean),
    Column("default_level", mcp_permission_level_enum),
)

team_integrations_table = Table(
    "team_integrations",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("team_id", UUID(as_uuid=False)),
    Column("installed_server_id", UUID(as_uuid=False)),
    Column("shared_with_all_members", Boolean),
)

tool_calls_table = Table(
    "tool_calls",
    metadata,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("created_at", DateTime(timezone=True), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("run_id", UUID(as_uuid=False)),
    Column("team_session_id", UUID(as_uuid=False)),
    Column("agent_id", UUID(as_uuid=False)),
    Column("installed_server_id", UUID(as_uuid=False)),
    Column("tool_name", Text),
    Column("status", tool_call_status_enum),
    Column("arguments", JSONB),
    Column("result_preview", Text),
    Column("result_bytes", Integer),
    Column("duration_ms", Integer),
    Column("error_message", Text),
    Column("denial_reason", Text),
    Column("attempt", Integer),
)

tool_logs_table = Table(
    "tool_logs",
    metadata,
    # Identity column — never supplied on insert.
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("created_at", DateTime(timezone=True), primary_key=True),
    Column("workspace_id", UUID(as_uuid=False)),
    Column("tool_call_id", UUID(as_uuid=False)),
    Column("installed_server_id", UUID(as_uuid=False)),
    Column("level", Text),
    Column("message", Text),
    Column("context", JSONB),
)
