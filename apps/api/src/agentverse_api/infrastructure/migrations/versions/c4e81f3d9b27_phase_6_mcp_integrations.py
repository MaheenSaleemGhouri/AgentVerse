"""phase 6: mcp integrations & the tool-execution boundary

Revision ID: c4e81f3d9b27
Revises: b3d70e2c1a45
Create Date: 2026-07-27

Eleven tables for consuming third-party MCP servers. Two layers:
`mcp_servers` is the platform-wide catalog of what *could* be installed;
`installed_servers` is a workspace's installation of one. Adding support
for a service is a catalog row, not a module — see ADR-0010 and
docs/security/threat-model-tool-execution.md.

Additive and reversible. Nothing existing is altered, so a rollback to
`b3d70e2c1a45` cannot break already-deployed code (Rule 19).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c4e81f3d9b27"
down_revision = "b3d70e2c1a45"
branch_labels = None
depends_on = None


mcp_transport = postgresql.ENUM(
    "stdio", "sse", "streamable_http", name="mcp_transport", create_type=False
)
mcp_availability = postgresql.ENUM(
    "official", "community", "custom_required", name="mcp_availability", create_type=False
)
mcp_auth_scheme = postgresql.ENUM(
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
mcp_install_status = postgresql.ENUM(
    "pending_auth", "active", "disabled", "error", name="mcp_install_status", create_type=False
)
mcp_health_status = postgresql.ENUM(
    "healthy", "degraded", "unreachable", "unknown", name="mcp_health_status", create_type=False
)
mcp_permission_level = postgresql.ENUM(
    "read_only", "read_write", "admin", name="mcp_permission_level", create_type=False
)
tool_call_status = postgresql.ENUM(
    "success",
    "error",
    "timeout",
    "denied",
    "circuit_open",
    "cached",
    name="tool_call_status",
    create_type=False,
)

_ENUMS = (
    mcp_transport,
    mcp_availability,
    mcp_auth_scheme,
    mcp_install_status,
    mcp_health_status,
    mcp_permission_level,
    tool_call_status,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in _ENUMS:
        enum.create(bind, checkfirst=True)

    # --- mcp_servers: the catalog ---------------------------------------
    # No `workspace_id`, deliberately. A tenant-owned table without one is
    # normally a bug (CLAUDE.md §8); the catalog is platform data, the
    # same for every tenant, and the exemption is recorded in ADR-0010.
    op.create_table(
        "mcp_servers",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("transport", mcp_transport, nullable=False),
        sa.Column("availability", mcp_availability, nullable=False),
        sa.Column("auth_scheme", mcp_auth_scheme, nullable=False),
        # STDIO entries only, always from this row. A user-supplied
        # command would be remote code execution on the worker fleet.
        sa.Column("command", sa.Text(), nullable=True),
        sa.Column(
            "command_args",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("endpoint_url", sa.Text(), nullable=True),
        sa.Column(
            "required_credentials",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "oauth_scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("documentation_url", sa.Text(), nullable=True),
        sa.Column("icon_slug", sa.Text(), nullable=True),
        sa.Column("is_deprecated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_mcp_server_slug"),
    )
    op.create_index("ix_mcp_servers_category", "mcp_servers", ["category"])
    # The marketplace's default view: installable, non-deprecated.
    op.create_index(
        "ix_mcp_servers_installable",
        "mcp_servers",
        ["availability"],
        postgresql_where=sa.text("is_deprecated = false"),
    )

    # --- installed_servers ----------------------------------------------
    op.create_table(
        "installed_servers",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Null for a custom user-registered server. RESTRICT so removing
        # a catalog entry a workspace has installed fails loudly rather
        # than orphaning the installation.
        sa.Column(
            "mcp_server_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("mcp_servers.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("transport", mcp_transport, nullable=False),
        sa.Column("endpoint_url", sa.Text(), nullable=True),
        sa.Column("status", mcp_install_status, nullable=False, server_default="pending_auth"),
        sa.Column("health", mcp_health_status, nullable=False, server_default="unknown"),
        # Non-secret settings only — this column is readable by every
        # endpoint that returns a server. Secrets go in `credentials`.
        sa.Column(
            "config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column(
            "discovered_tools",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("tools_discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column(
            "installed_by_user_id",
            # users.id is better-auth's and is TEXT, not uuid, unlike
            # every AgentVerse-owned primary key.
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_installed_servers_workspace", "installed_servers", ["workspace_id", "created_at"]
    )
    # The hot subset the runtime resolves per tool call.
    op.create_index(
        "ix_installed_servers_active",
        "installed_servers",
        ["workspace_id", "status"],
        postgresql_where=sa.text("status = 'active' AND deleted_at IS NULL"),
    )

    # --- server_versions -------------------------------------------------
    op.create_table(
        "server_versions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "installed_server_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("installed_servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("tools", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "changed_tool_names",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_server_versions_workspace", "server_versions", ["workspace_id"])
    op.create_index(
        "ix_server_versions_server", "server_versions", ["installed_server_id", "created_at"]
    )

    # --- credentials -----------------------------------------------------
    # Envelope encryption: `ciphertext` is the secret under a per-row data
    # key, `wrapped_dek` is that key under a runtime-environment key. A
    # Postgres dump alone yields nothing usable. There is no plaintext
    # column and no API path that returns one (ADR-0010).
    op.create_table(
        "credentials",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "installed_server_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("installed_servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("auth_scheme", mcp_auth_scheme, nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("wrapped_dek", sa.LargeBinary(), nullable=False),
        # Which environment key wrapped the DEK, so rotating the root key
        # does not require re-encrypting every row at once.
        sa.Column("key_version", sa.Text(), nullable=False),
        # Last four characters only. A prefix would be a search key.
        sa.Column("hint", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("installed_server_id", "key", name="uq_credential_server_key"),
    )
    op.create_index("ix_credentials_workspace", "credentials", ["workspace_id"])
    op.create_index("ix_credentials_server", "credentials", ["installed_server_id"])
    # Rotation sweep target: credentials with a known expiry.
    op.create_index(
        "ix_credentials_expiring",
        "credentials",
        ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )

    # --- permissions -----------------------------------------------------
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "installed_server_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("installed_servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("level", mcp_permission_level, nullable=False, server_default="read_only"),
        sa.Column(
            "allowed_tools",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("cache_ttl_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_calls_per_run", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "granted_by_user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # "At most one subject" is the kind of invariant that decays if
        # left to convention.
        sa.CheckConstraint(
            "NOT (agent_id IS NOT NULL AND team_id IS NOT NULL)",
            name="ck_permission_single_subject",
        ),
    )
    op.create_index("ix_permissions_workspace", "permissions", ["workspace_id"])
    op.create_index("ix_permissions_server", "permissions", ["installed_server_id"])
    # The resolution query the boundary runs per tool call.
    op.create_index(
        "ix_permissions_agent",
        "permissions",
        ["agent_id"],
        postgresql_where=sa.text("agent_id IS NOT NULL"),
    )
    op.create_index(
        "ix_permissions_team",
        "permissions",
        ["team_id"],
        postgresql_where=sa.text("team_id IS NOT NULL"),
    )

    # --- tool_calls (partitioned) ----------------------------------------
    # The highest-volume table this phase adds. Partitioned by created_at
    # from this, its first migration (CLAUDE.md §8), matching
    # agent_run_steps and execution_events.
    op.create_table(
        "tool_calls",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("team_session_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("installed_server_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("status", tool_call_status, nullable=False),
        sa.Column("arguments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        # Truncated to the output cap. The full result is untrusted
        # third-party content; an unbounded store of it is a liability.
        sa.Column("result_preview", sa.Text(), nullable=True),
        sa.Column("result_bytes", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        # Which rule rejected a denied call. A blocked SSRF attempt that
        # left no row would make the egress control unauditable.
        sa.Column("denial_reason", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id", "created_at"),
        postgresql_partition_by="RANGE (created_at)",
    )
    op.create_index("ix_tool_calls_workspace", "tool_calls", ["workspace_id", "created_at"])
    op.create_index(
        "ix_tool_calls_run",
        "tool_calls",
        ["run_id"],
        postgresql_where=sa.text("run_id IS NOT NULL"),
    )
    op.create_index("ix_tool_calls_server", "tool_calls", ["installed_server_id", "created_at"])
    # The failure view the runtime dashboard opens on.
    op.create_index(
        "ix_tool_calls_failures",
        "tool_calls",
        ["workspace_id", "created_at"],
        postgresql_where=sa.text("status IN ('error', 'timeout', 'denied', 'circuit_open')"),
    )
    op.execute("CREATE TABLE tool_calls_default PARTITION OF tool_calls DEFAULT")

    # --- tool_logs (partitioned) -----------------------------------------
    op.create_table(
        "tool_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("tool_call_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("installed_server_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "context", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.PrimaryKeyConstraint("id", "created_at"),
        postgresql_partition_by="RANGE (created_at)",
    )
    op.create_index("ix_tool_logs_workspace", "tool_logs", ["workspace_id", "created_at"])
    op.create_index(
        "ix_tool_logs_call",
        "tool_logs",
        ["tool_call_id"],
        postgresql_where=sa.text("tool_call_id IS NOT NULL"),
    )
    op.execute("CREATE TABLE tool_logs_default PARTITION OF tool_logs DEFAULT")

    # --- tool_metrics ----------------------------------------------------
    op.create_table(
        "tool_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "installed_server_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("installed_servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("denied_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timeout_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_duration_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("p95_duration_ms", sa.Integer(), nullable=True),
        # Upsert target for the rollup job.
        sa.UniqueConstraint(
            "installed_server_id", "tool_name", "bucket_start", name="uq_tool_metric_bucket"
        ),
    )
    op.create_index("ix_tool_metrics_workspace", "tool_metrics", ["workspace_id"])
    op.create_index("ix_tool_metrics_server", "tool_metrics", ["installed_server_id"])
    op.create_index("ix_tool_metrics_bucket", "tool_metrics", ["bucket_start"])

    # --- oauth_sessions --------------------------------------------------
    op.create_table(
        "oauth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "installed_server_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("installed_servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.Text(), nullable=False),
        # PKCE verifier, encrypted for the same reason the token is —
        # it is itself a credential until the exchange completes.
        sa.Column("code_verifier_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("wrapped_dek", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.Text(), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column(
            "requested_scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "started_by_user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # Unique so a replayed callback cannot match twice.
        sa.UniqueConstraint("state", name="uq_oauth_session_state"),
    )
    op.create_index("ix_oauth_sessions_workspace", "oauth_sessions", ["workspace_id"])
    # Sweep target for the expiry job — an abandoned exchange leaves a
    # live verifier behind.
    op.create_index("ix_oauth_sessions_expiry", "oauth_sessions", ["expires_at"])

    # --- workspace_integrations ------------------------------------------
    op.create_table(
        "workspace_integrations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "installed_server_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("installed_servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("members_may_grant", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "default_level", mcp_permission_level, nullable=False, server_default="read_only"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "installed_server_id", name="uq_workspace_integration"),
    )
    op.create_index(
        "ix_workspace_integrations_workspace", "workspace_integrations", ["workspace_id"]
    )

    # --- team_integrations -----------------------------------------------
    op.create_table(
        "team_integrations",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "installed_server_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("installed_servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "shared_with_all_members", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("team_id", "installed_server_id", name="uq_team_integration"),
    )
    op.create_index("ix_team_integrations_workspace", "team_integrations", ["workspace_id"])
    op.create_index("ix_team_integrations_team", "team_integrations", ["team_id"])


def downgrade() -> None:
    # Reverse creation order so foreign keys never block a drop.
    op.drop_table("team_integrations")
    op.drop_table("workspace_integrations")
    op.drop_table("oauth_sessions")
    op.drop_table("tool_metrics")
    op.execute("DROP TABLE IF EXISTS tool_logs_default")
    op.drop_table("tool_logs")
    op.execute("DROP TABLE IF EXISTS tool_calls_default")
    op.drop_table("tool_calls")
    op.drop_table("permissions")
    op.drop_table("credentials")
    op.drop_table("server_versions")
    op.drop_table("installed_servers")
    op.drop_table("mcp_servers")

    # Dropped explicitly: Alembic's drop_table leaves the Postgres type
    # behind, and a re-run of upgrade() would then fail on "type already
    # exists" — which is how a downgrade that "worked" turns out to be
    # untested.
    for enum_name in (
        "tool_call_status",
        "mcp_permission_level",
        "mcp_health_status",
        "mcp_install_status",
        "mcp_auth_scheme",
        "mcp_availability",
        "mcp_transport",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
