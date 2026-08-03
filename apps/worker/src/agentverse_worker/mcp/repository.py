"""Resolves an agent's or team's MCP grants, and records tool calls.

Two responsibilities, both workspace-scoped by construction: every method
takes `workspace_id` as a required keyword and every query filters on it,
so a cross-tenant read is unexpressible here rather than merely checked
(Rule 11).

Credentials are decrypted **at resolution time**, held only long enough
to build the connection spec, and never returned to a caller that could
log them. The vault's AAD binds each ciphertext to its
`(workspace, server, key)` row, so a credential moved between rows fails
to decrypt rather than silently working.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from agentverse_shared.observability.metrics import record_credential_unseal_failure
from agentverse_shared.security.envelope import (
    CredentialCryptoError,
    CredentialVault,
    SealedSecret,
    credential_aad,
)
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_worker.mcp.factory import ServerConnectionSpec, credential_placement
from agentverse_worker.mcp.tables import (
    credentials_table,
    installed_servers_table,
    mcp_servers_table,
    permissions_table,
    team_integrations_table,
    tool_calls_table,
    tool_logs_table,
    workspace_integrations_table,
)
from agentverse_worker.tools.boundary import ToolDefinition, ToolGrant

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ResolvedIntegration:
    """One installed server an agent may use, ready to connect.

    Bundles the connection spec with the grant that governs it, because
    the two are only ever used together — separating them would let a
    caller connect to a server without carrying its limits.
    """

    spec: ServerConnectionSpec
    grant: ToolGrant
    #: Discovery cached at install time, keyed by name. The boundary
    #: validates against these schemas; a tool absent here is refused.
    tools: dict[str, ToolDefinition] = field(default_factory=dict)


class IntegrationRepositoryProtocol(Protocol):
    """What the run path depends on, so the wiring is unit-testable
    against a fake without Postgres (CLAUDE.md §11).
    """

    async def resolve_for_agent(
        self, *, workspace_id: str, agent_id: str
    ) -> list[ResolvedIntegration]: ...

    async def resolve_for_team(
        self, *, workspace_id: str, team_id: str, agent_id: str
    ) -> list[ResolvedIntegration]: ...

    #: Declared with its full signature rather than `**kwargs` so this
    #: Protocol structurally satisfies the boundary's `ToolCallRecorder`.
    #: A `**kwargs` shorthand type-checks against nothing and would have
    #: let a renamed field through silently.
    async def record_call(
        self,
        *,
        workspace_id: str,
        run_id: str | None,
        team_session_id: str | None,
        agent_id: str | None,
        installed_server_id: str | None,
        tool_name: str,
        status: str,
        arguments: dict[str, Any],
        result_preview: str | None,
        result_bytes: int | None,
        duration_ms: int | None,
        error_message: str | None,
        denial_reason: str | None,
        attempt: int,
    ) -> None: ...


def _to_tool_definitions(raw: Any) -> dict[str, ToolDefinition]:
    """Rebuilds discovery from the stored JSONB.

    Tolerant of shape: the column is written by a previous version of
    this code, and a malformed entry should cost one tool rather than
    the whole server.
    """
    tools: dict[str, ToolDefinition] = {}
    if not isinstance(raw, list):
        return tools
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        schema = entry.get("input_schema")
        tools[name] = ToolDefinition(
            name=name,
            description=str(entry.get("description") or ""),
            input_schema=schema if isinstance(schema, dict) else {},
            # Missing means an older row written before the flag existed.
            # Defaults to mutating, matching `infer_is_mutating`'s bias:
            # the failure directions are not symmetric.
            is_mutating=bool(entry.get("is_mutating", True)),
        )
    return tools


class WorkerIntegrationRepository:
    def __init__(self, session: AsyncSession, vault: CredentialVault) -> None:
        self._session = session
        self._vault = vault

    async def _load_credentials(
        self, *, workspace_id: str, installed_server_id: str
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Decrypts this server's credentials into env and headers.

        A credential that fails to decrypt is skipped with a warning
        rather than raising: one unreadable secret should cost that
        server's auth, not the whole run. The failure surfaces as an auth
        error from the third party, which is the accurate symptom.
        """
        result = await self._session.execute(
            select(credentials_table).where(
                credentials_table.c.workspace_id == workspace_id,
                credentials_table.c.installed_server_id == installed_server_id,
            )
        )
        env: dict[str, str] = {}
        headers: dict[str, str] = {}

        for row in result.mappings():
            expires_at = row["expires_at"]
            if expires_at is not None and expires_at <= datetime.now(UTC):
                logger.warning(
                    "credential_expired workspace_id=%s server_id=%s key=%s",
                    workspace_id,
                    installed_server_id,
                    row["key"],
                )
                continue
            try:
                value = self._vault.open(
                    SealedSecret(
                        ciphertext=row["ciphertext"],
                        wrapped_dek=row["wrapped_dek"],
                        key_version=row["key_version"],
                    ),
                    associated_data=credential_aad(
                        workspace_id=workspace_id,
                        installed_server_id=installed_server_id,
                        key=row["key"],
                    ),
                )
            except CredentialCryptoError:
                # Steady state is zero, which is what makes this alertable
                # at a single event: the only ways here are a KEK mismatch
                # between apps/api and apps/worker, or an AAD mismatch —
                # and an AAD mismatch means a credential row was moved
                # between workspaces.
                record_credential_unseal_failure()
                # Never logs the value, and the exception carries no
                # detail about why — see `CredentialCryptoError`.
                logger.warning(
                    "credential_unreadable workspace_id=%s server_id=%s key=%s",
                    workspace_id,
                    installed_server_id,
                    row["key"],
                )
                continue

            entry_env, entry_headers = credential_placement(
                str(row["auth_scheme"]), str(row["key"]), value
            )
            env.update(entry_env)
            headers.update(entry_headers)

        return env, headers

    async def _build(self, *, workspace_id: str, row: Any, permission: Any) -> ResolvedIntegration:
        installed_id = row["installed_server_id"]
        env, headers = await self._load_credentials(
            workspace_id=workspace_id, installed_server_id=installed_id
        )

        # A catalog-backed install takes its command and endpoint from
        # the catalog row, never from the installation — that is what
        # makes stdio safe (ADR-0010).
        is_catalog = row["mcp_server_id"] is not None
        spec = ServerConnectionSpec(
            installed_server_id=installed_id,
            workspace_id=workspace_id,
            display_name=row["display_name"],
            transport=str(row["transport"]),
            command=row["catalog_command"] if is_catalog else None,
            command_args=tuple(row["catalog_command_args"] or ()) if is_catalog else (),
            env=env,
            endpoint_url=(row["catalog_endpoint_url"] if is_catalog else row["endpoint_url"]),
            headers=headers,
            is_catalog_entry=is_catalog,
            allowed_tools=tuple(permission["allowed_tools"] or ()),
        )
        grant = ToolGrant(
            installed_server_id=installed_id,
            level=str(permission["level"]),
            allowed_tools=tuple(permission["allowed_tools"] or ()),
            timeout_seconds=int(permission["timeout_seconds"]),
            max_retries=int(permission["max_retries"]),
            cache_ttl_seconds=int(permission["cache_ttl_seconds"]),
            max_calls_per_run=int(permission["max_calls_per_run"]),
            fallback_tools=dict(permission["fallback_tools"] or {}),
        )
        return ResolvedIntegration(
            spec=spec, grant=grant, tools=_to_tool_definitions(row["discovered_tools"])
        )

    def _usable_servers_query(self, workspace_id: str) -> Any:
        """Installations this workspace may actually use.

        Three conditions, all of which must hold: the install is active
        and not soft-deleted, and the workspace has not disabled it.
        `workspace_integrations` is an outer join because an install
        without an explicit policy row defaults to enabled.
        """
        installed = installed_servers_table
        catalog = mcp_servers_table
        policy = workspace_integrations_table

        return (
            select(
                installed.c.id.label("installed_server_id"),
                installed.c.mcp_server_id,
                installed.c.display_name,
                installed.c.transport,
                installed.c.endpoint_url,
                installed.c.discovered_tools,
                catalog.c.command.label("catalog_command"),
                catalog.c.command_args.label("catalog_command_args"),
                catalog.c.endpoint_url.label("catalog_endpoint_url"),
            )
            .select_from(
                installed.outerjoin(catalog, catalog.c.id == installed.c.mcp_server_id).outerjoin(
                    policy, policy.c.installed_server_id == installed.c.id
                )
            )
            .where(
                installed.c.workspace_id == workspace_id,
                installed.c.status == "active",
                installed.c.deleted_at.is_(None),
                or_(policy.c.is_enabled.is_(None), policy.c.is_enabled.is_(True)),
            )
        )

    async def resolve_for_agent(
        self, *, workspace_id: str, agent_id: str
    ) -> list[ResolvedIntegration]:
        """Servers this agent may use, with the grant governing each.

        A grant scoped to this agent wins over a workspace-wide one:
        narrowing an individual agent must not be undone by the broader
        default. Ordered by `priority` so a grant that wants to be tried
        first is, then by id for a stable order.
        """
        permission = permissions_table
        rows = await self._session.execute(
            self._usable_servers_query(workspace_id)
            .add_columns(
                permission.c.level,
                permission.c.allowed_tools,
                permission.c.timeout_seconds,
                permission.c.max_retries,
                permission.c.cache_ttl_seconds,
                permission.c.max_calls_per_run,
                permission.c.priority,
                permission.c.agent_id,
                permission.c.fallback_tools,
            )
            .join(
                permission,
                permission.c.installed_server_id == installed_servers_table.c.id,
            )
            .where(
                permission.c.workspace_id == workspace_id,
                # Agent-specific grant, or a workspace-wide one (neither
                # agent nor team set).
                or_(
                    permission.c.agent_id == agent_id,
                    (permission.c.agent_id.is_(None)) & (permission.c.team_id.is_(None)),
                ),
            )
            .order_by(permission.c.priority, installed_servers_table.c.id)
        )

        # An agent-specific grant shadows the workspace-wide one for the
        # same server — resolved here rather than in SQL because the rule
        # is a preference, not a filter, and expressing it as a window
        # function would make it harder to read than it is worth.
        best: dict[str, Any] = {}
        for row in rows.mappings():
            key = row["installed_server_id"]
            existing = best.get(key)
            if existing is None or (existing["agent_id"] is None and row["agent_id"] is not None):
                best[key] = row

        return [
            await self._build(workspace_id=workspace_id, row=row, permission=row)
            for row in best.values()
        ]

    async def resolve_for_team(
        self, *, workspace_id: str, team_id: str, agent_id: str
    ) -> list[ResolvedIntegration]:
        """Servers a team member may use.

        The union of the team's shared integrations and the member's own
        agent grants — a team sharing a server does not remove a member's
        individually granted one, and vice versa. Deduplicated by server,
        with the agent's own grant preferred, since it is the more
        specific statement of intent.
        """
        agent_side = {
            integration.spec.installed_server_id: integration
            for integration in await self.resolve_for_agent(
                workspace_id=workspace_id, agent_id=agent_id
            )
        }

        permission = permissions_table
        team_link = team_integrations_table
        rows = await self._session.execute(
            self._usable_servers_query(workspace_id)
            .add_columns(
                permission.c.level,
                permission.c.allowed_tools,
                permission.c.timeout_seconds,
                permission.c.max_retries,
                permission.c.cache_ttl_seconds,
                permission.c.max_calls_per_run,
                permission.c.fallback_tools,
            )
            .join(team_link, team_link.c.installed_server_id == installed_servers_table.c.id)
            .join(
                permission,
                permission.c.installed_server_id == installed_servers_table.c.id,
            )
            .where(
                team_link.c.workspace_id == workspace_id,
                team_link.c.team_id == team_id,
                team_link.c.shared_with_all_members.is_(True),
                permission.c.workspace_id == workspace_id,
                permission.c.team_id == team_id,
            )
            .order_by(permission.c.priority, installed_servers_table.c.id)
        )

        for row in rows.mappings():
            server_id = row["installed_server_id"]
            if server_id in agent_side:
                continue
            agent_side[server_id] = await self._build(
                workspace_id=workspace_id, row=row, permission=row
            )

        return list(agent_side.values())

    async def record_call(
        self,
        *,
        workspace_id: str,
        run_id: str | None,
        team_session_id: str | None,
        agent_id: str | None,
        installed_server_id: str | None,
        tool_name: str,
        status: str,
        arguments: dict[str, Any],
        result_preview: str | None,
        result_bytes: int | None,
        duration_ms: int | None,
        error_message: str | None,
        denial_reason: str | None,
        attempt: int,
    ) -> None:
        """Writes one `tool_calls` row.

        Called for every outcome including denials — a blocked attempt
        that left no row would make the egress and permission controls
        unauditable, which is most of their value (ADR-0010).
        """
        await self._session.execute(
            tool_calls_table.insert().values(
                id=str(uuid.uuid4()),
                created_at=datetime.now(UTC),
                workspace_id=workspace_id,
                run_id=run_id,
                team_session_id=team_session_id,
                agent_id=agent_id,
                installed_server_id=installed_server_id,
                tool_name=tool_name,
                status=status,
                arguments=arguments,
                result_preview=result_preview,
                result_bytes=result_bytes,
                duration_ms=duration_ms,
                error_message=error_message,
                denial_reason=denial_reason,
                attempt=attempt,
            )
        )
        await self._session.commit()

    async def record_log(
        self,
        *,
        workspace_id: str,
        installed_server_id: str | None,
        level: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        await self._session.execute(
            tool_logs_table.insert().values(
                created_at=datetime.now(UTC),
                workspace_id=workspace_id,
                installed_server_id=installed_server_id,
                level=level,
                message=message,
                context=context or {},
            )
        )
        await self._session.commit()

    async def list_active_installations(self) -> list[ServerConnectionSpec]:
        """Every install the scheduled health sweep should probe.

        Deliberately platform-wide, not `workspace_id`-scoped like every
        other query in this file: a health sweep's job is "is this server
        reachable", which is a fact about the server, not about which
        workspace is asking. `workspace_id` is still carried on every
        returned spec (Rule 11) — nothing here reads or returns
        cross-tenant data, it just reads across tenants by design, the
        same exemption ADR-0010 already grants the `mcp_servers` catalog.

        No permission join: connecting to probe reachability is not the
        same operation as a grant-scoped tool call, and one server with a
        missing/misconfigured permission row must not disappear from
        health reporting because of it.
        """
        installed = installed_servers_table
        catalog = mcp_servers_table
        result = await self._session.execute(
            select(
                installed.c.id.label("installed_server_id"),
                installed.c.workspace_id,
                installed.c.mcp_server_id,
                installed.c.display_name,
                installed.c.transport,
                installed.c.endpoint_url,
                catalog.c.command.label("catalog_command"),
                catalog.c.command_args.label("catalog_command_args"),
                catalog.c.endpoint_url.label("catalog_endpoint_url"),
            )
            .select_from(installed.outerjoin(catalog, catalog.c.id == installed.c.mcp_server_id))
            .where(installed.c.status == "active", installed.c.deleted_at.is_(None))
        )

        specs: list[ServerConnectionSpec] = []
        for row in result.mappings():
            workspace_id = str(row["workspace_id"])
            installed_id = str(row["installed_server_id"])
            env, headers = await self._load_credentials(
                workspace_id=workspace_id, installed_server_id=installed_id
            )
            is_catalog = row["mcp_server_id"] is not None
            specs.append(
                ServerConnectionSpec(
                    installed_server_id=installed_id,
                    workspace_id=workspace_id,
                    display_name=row["display_name"],
                    transport=str(row["transport"]),
                    command=row["catalog_command"] if is_catalog else None,
                    command_args=(tuple(row["catalog_command_args"] or ()) if is_catalog else ()),
                    env=env,
                    endpoint_url=(
                        row["catalog_endpoint_url"] if is_catalog else row["endpoint_url"]
                    ),
                    headers=headers,
                    is_catalog_entry=is_catalog,
                )
            )
        return specs

    async def record_health_check(
        self,
        *,
        installed_server_id: str,
        health: str,
        checked_at: datetime,
        error: str | None,
    ) -> None:
        """Persists one `check_health` result.

        Writes `health`/`last_health_check_at`/`last_error` only — never
        `status`. A server the sweep finds unreachable stays `active`
        with `health="unreachable"`: those are different facts (whether
        the workspace wants it enabled vs. whether it currently answers),
        and collapsing them would silently disable a server a transient
        network blip made unreachable for one sweep.
        """
        await self._session.execute(
            installed_servers_table.update()
            .where(installed_servers_table.c.id == installed_server_id)
            .values(health=health, last_health_check_at=checked_at, last_error=error)
        )
        await self._session.commit()
