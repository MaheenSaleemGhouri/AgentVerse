"""Postgres implementation of `IntegrationRepository`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.infrastructure.sql_result import affected
from agentverse_api.orchestration_service.domain.integration_entities import (
    AuthScheme,
    CredentialRef,
    HealthStatus,
    InstalledServer,
    InstallStatus,
    IntegrationPermission,
    McpAvailability,
    McpServer,
    McpServerTool,
    McpTransport,
    PermissionLevel,
    ToolCall,
    ToolCallStatus,
)
from agentverse_api.orchestration_service.infrastructure.models import (
    CredentialModel,
    InstalledServerModel,
    IntegrationPermissionModel,
    McpServerModel,
    OauthSessionModel,
    ServerVersionModel,
    ToolCallModel,
)


def _to_tool(raw: dict[str, Any]) -> McpServerTool:
    schema = raw.get("input_schema")
    return McpServerTool(
        name=str(raw.get("name", "")),
        description=str(raw.get("description") or ""),
        input_schema=schema if isinstance(schema, dict) else {},
        # Missing means a row written before the flag existed. Defaults
        # to mutating, matching the worker's inference bias — the failure
        # directions are not symmetric.
        is_mutating=bool(raw.get("is_mutating", True)),
    )


def _to_catalog(row: McpServerModel) -> McpServer:
    return McpServer(
        id=row.id,
        slug=row.slug,
        name=row.name,
        description=row.description,
        category=row.category,
        transport=row.transport,
        availability=row.availability,
        auth_scheme=row.auth_scheme,
        command=row.command,
        command_args=list(row.command_args or []),
        endpoint_url=row.endpoint_url,
        required_credentials=list(row.required_credentials or []),
        oauth_scopes=list(row.oauth_scopes or []),
        documentation_url=row.documentation_url,
        icon_slug=row.icon_slug,
        is_deprecated=row.is_deprecated,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_installed(row: InstalledServerModel) -> InstalledServer:
    return InstalledServer(
        id=row.id,
        workspace_id=row.workspace_id,
        mcp_server_id=row.mcp_server_id,
        display_name=row.display_name,
        transport=row.transport,
        endpoint_url=row.endpoint_url,
        status=row.status,
        health=row.health,
        config=row.config,
        discovered_tools=[
            _to_tool(entry) for entry in (row.discovered_tools or []) if isinstance(entry, dict)
        ],
        tools_discovered_at=row.tools_discovered_at,
        last_health_check_at=row.last_health_check_at,
        last_error=row.last_error,
        version=row.version,
        installed_by_user_id=row.installed_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_credential_ref(row: CredentialModel) -> CredentialRef:
    """Note what is absent: no ciphertext, no wrapped key, no value.

    The domain type has no field for a secret, so a future endpoint
    cannot accidentally serialise one.
    """
    return CredentialRef(
        id=row.id,
        workspace_id=row.workspace_id,
        installed_server_id=row.installed_server_id,
        key=row.key,
        auth_scheme=row.auth_scheme,
        hint=row.hint,
        expires_at=row.expires_at,
        last_rotated_at=row.last_rotated_at,
        created_at=row.created_at,
    )


def _to_permission(row: IntegrationPermissionModel) -> IntegrationPermission:
    return IntegrationPermission(
        id=row.id,
        workspace_id=row.workspace_id,
        installed_server_id=row.installed_server_id,
        agent_id=row.agent_id,
        team_id=row.team_id,
        level=row.level,
        allowed_tools=list(row.allowed_tools or []),
        timeout_seconds=row.timeout_seconds,
        max_retries=row.max_retries,
        cache_ttl_seconds=row.cache_ttl_seconds,
        max_calls_per_run=row.max_calls_per_run,
        priority=row.priority,
        granted_by_user_id=row.granted_by_user_id,
        created_at=row.created_at,
    )


def _to_tool_call(row: ToolCallModel) -> ToolCall:
    return ToolCall(
        id=row.id,
        workspace_id=row.workspace_id,
        run_id=row.run_id,
        team_session_id=row.team_session_id,
        agent_id=row.agent_id,
        installed_server_id=row.installed_server_id,
        tool_name=row.tool_name,
        status=ToolCallStatus(row.status),
        arguments=row.arguments,
        result_preview=row.result_preview,
        result_bytes=row.result_bytes,
        duration_ms=row.duration_ms,
        error_message=row.error_message,
        denial_reason=row.denial_reason,
        attempt=row.attempt,
        created_at=row.created_at,
    )


class SqlIntegrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- catalog ----------------------------------------------------------

    async def list_catalog(
        self, *, category: str | None = None, query: str | None = None
    ) -> list[McpServer]:
        statement = select(McpServerModel).where(McpServerModel.is_deprecated.is_(False))
        if category:
            statement = statement.where(McpServerModel.category == category)
        if query:
            # Simple ILIKE rather than full-text: the catalog is dozens of
            # rows, not millions, and a tsvector index here would be
            # infrastructure for a problem that does not exist.
            pattern = f"%{query}%"
            statement = statement.where(
                or_(
                    McpServerModel.name.ilike(pattern),
                    McpServerModel.description.ilike(pattern),
                    McpServerModel.slug.ilike(pattern),
                )
            )
        result = await self._session.execute(
            statement.order_by(McpServerModel.category, McpServerModel.name)
        )
        return [_to_catalog(row) for row in result.scalars()]

    async def get_catalog_entry(self, *, server_id: str) -> McpServer | None:
        row = await self._session.get(McpServerModel, server_id)
        return _to_catalog(row) if row else None

    async def get_catalog_entry_by_slug(self, *, slug: str) -> McpServer | None:
        result = await self._session.execute(
            select(McpServerModel).where(McpServerModel.slug == slug)
        )
        row = result.scalar_one_or_none()
        return _to_catalog(row) if row else None

    async def upsert_catalog_entry(self, *, entry: dict[str, Any]) -> McpServer:
        now = datetime.now(UTC)
        values = {**entry, "id": str(uuid.uuid4()), "created_at": now, "updated_at": now}
        # Everything except identity and creation time is refreshed, so
        # editing a description and re-running the seed updates the row.
        updatable = {k: v for k, v in entry.items() if k != "slug"}
        statement = (
            pg_insert(McpServerModel)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_mcp_server_slug", set_={**updatable, "updated_at": now}
            )
            .returning(McpServerModel)
        )
        result = await self._session.execute(statement)
        await self._session.commit()
        return _to_catalog(result.scalar_one())

    # --- installations ----------------------------------------------------

    def _live_installs(self, workspace_id: str) -> Select[Any]:
        return select(InstalledServerModel).where(
            InstalledServerModel.workspace_id == workspace_id,
            InstalledServerModel.deleted_at.is_(None),
        )

    async def install(
        self,
        *,
        workspace_id: str,
        mcp_server_id: str | None,
        display_name: str,
        transport: str,
        endpoint_url: str | None,
        config: dict[str, Any],
        status: InstallStatus,
        installed_by_user_id: str,
    ) -> InstalledServer:
        now = datetime.now(UTC)
        model = InstalledServerModel(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            mcp_server_id=mcp_server_id,
            display_name=display_name,
            transport=McpTransport(transport),
            endpoint_url=endpoint_url,
            status=status,
            health=HealthStatus.UNKNOWN,
            config=config,
            discovered_tools=[],
            installed_by_user_id=installed_by_user_id,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        await self._session.commit()
        return _to_installed(model)

    async def list_installed(self, *, workspace_id: str) -> list[InstalledServer]:
        result = await self._session.execute(
            self._live_installs(workspace_id).order_by(InstalledServerModel.created_at.desc())
        )
        return [_to_installed(row) for row in result.scalars()]

    async def count_installed(self, *, workspace_id: str) -> int:
        """Live MCP installations, for plan-limit enforcement.

        Built from `_live_installs` so billing counts exactly what the
        integrations page lists (Rule 5).
        """
        result = await self._session.execute(
            select(func.count()).select_from(self._live_installs(workspace_id).subquery())
        )
        return int(result.scalar_one())

    async def get_installed(
        self, *, workspace_id: str, installed_server_id: str
    ) -> InstalledServer | None:
        result = await self._session.execute(
            self._live_installs(workspace_id).where(InstalledServerModel.id == installed_server_id)
        )
        row = result.scalar_one_or_none()
        return _to_installed(row) if row else None

    async def update_installed(
        self, *, workspace_id: str, installed_server_id: str, changes: dict[str, Any]
    ) -> InstalledServer | None:
        if changes:
            await self._session.execute(
                update(InstalledServerModel)
                .where(
                    InstalledServerModel.id == installed_server_id,
                    InstalledServerModel.workspace_id == workspace_id,
                    InstalledServerModel.deleted_at.is_(None),
                )
                .values(**changes, updated_at=datetime.now(UTC))
            )
            await self._session.commit()
        return await self.get_installed(
            workspace_id=workspace_id, installed_server_id=installed_server_id
        )

    async def uninstall(self, *, workspace_id: str, installed_server_id: str) -> bool:
        result = await self._session.execute(
            update(InstalledServerModel)
            .where(
                InstalledServerModel.id == installed_server_id,
                InstalledServerModel.workspace_id == workspace_id,
                InstalledServerModel.deleted_at.is_(None),
            )
            .values(
                deleted_at=datetime.now(UTC),
                # Disabled as well as deleted: the runtime resolves on
                # `status = 'active'`, so this stops in-flight grants
                # immediately rather than relying on the soft-delete
                # filter alone.
                status=InstallStatus.DISABLED,
            )
        )
        await self._session.commit()
        return affected(result)

    async def record_discovery(
        self,
        *,
        workspace_id: str,
        installed_server_id: str,
        tools: list[dict[str, Any]],
        version: str | None,
        health: HealthStatus,
        error: str | None,
        changed_tool_names: list[str],
    ) -> None:
        now = datetime.now(UTC)
        await self._session.execute(
            update(InstalledServerModel)
            .where(
                InstalledServerModel.id == installed_server_id,
                InstalledServerModel.workspace_id == workspace_id,
            )
            .values(
                discovered_tools=tools,
                tools_discovered_at=now,
                last_health_check_at=now,
                health=health,
                last_error=error,
                version=version,
                updated_at=now,
            )
        )
        # A version row only when the surface actually changed. Writing
        # one per discovery would bury the changes that matter under
        # hourly no-ops.
        if changed_tool_names or version:
            self._session.add(
                ServerVersionModel(
                    id=str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    installed_server_id=installed_server_id,
                    version=version or now.isoformat(),
                    tools=tools,
                    changed_tool_names=changed_tool_names,
                    created_at=now,
                )
            )
        await self._session.commit()

    # --- credentials ------------------------------------------------------

    async def put_credential(
        self,
        *,
        workspace_id: str,
        installed_server_id: str,
        key: str,
        auth_scheme: AuthScheme,
        ciphertext: bytes,
        wrapped_dek: bytes,
        key_version: str,
        hint: str,
        expires_at: datetime | None,
    ) -> CredentialRef:
        now = datetime.now(UTC)
        statement = (
            pg_insert(CredentialModel)
            .values(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                installed_server_id=installed_server_id,
                key=key,
                auth_scheme=auth_scheme,
                ciphertext=ciphertext,
                wrapped_dek=wrapped_dek,
                key_version=key_version,
                hint=hint,
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_credential_server_key",
                set_={
                    "ciphertext": ciphertext,
                    "wrapped_dek": wrapped_dek,
                    "key_version": key_version,
                    "hint": hint,
                    "expires_at": expires_at,
                    "auth_scheme": auth_scheme,
                    # Set on every write, including the first: "never
                    # rotated" and "rotated at creation" are the same
                    # fact, and a null here would read as the former.
                    "last_rotated_at": now,
                    "updated_at": now,
                },
            )
            .returning(CredentialModel)
        )
        result = await self._session.execute(statement)
        await self._session.commit()
        return _to_credential_ref(result.scalar_one())

    async def list_credential_refs(
        self, *, workspace_id: str, installed_server_id: str
    ) -> list[CredentialRef]:
        result = await self._session.execute(
            select(CredentialModel)
            .where(
                CredentialModel.workspace_id == workspace_id,
                CredentialModel.installed_server_id == installed_server_id,
            )
            .order_by(CredentialModel.key)
        )
        return [_to_credential_ref(row) for row in result.scalars()]

    async def delete_credential(
        self, *, workspace_id: str, installed_server_id: str, key: str
    ) -> bool:
        result = await self._session.execute(
            delete(CredentialModel).where(
                CredentialModel.workspace_id == workspace_id,
                CredentialModel.installed_server_id == installed_server_id,
                CredentialModel.key == key,
            )
        )
        await self._session.commit()
        return affected(result)

    # --- permissions ------------------------------------------------------

    async def grant(
        self,
        *,
        workspace_id: str,
        installed_server_id: str,
        agent_id: str | None,
        team_id: str | None,
        level: PermissionLevel,
        allowed_tools: list[str],
        limits: dict[str, int],
        granted_by_user_id: str,
    ) -> IntegrationPermission:
        now = datetime.now(UTC)
        model = IntegrationPermissionModel(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            installed_server_id=installed_server_id,
            agent_id=agent_id,
            team_id=team_id,
            level=level,
            allowed_tools=allowed_tools,
            timeout_seconds=limits.get("timeout_seconds", 30),
            max_retries=limits.get("max_retries", 2),
            cache_ttl_seconds=limits.get("cache_ttl_seconds", 0),
            max_calls_per_run=limits.get("max_calls_per_run", 50),
            priority=limits.get("priority", 0),
            granted_by_user_id=granted_by_user_id,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        await self._session.commit()
        return _to_permission(model)

    async def list_grants(
        self,
        *,
        workspace_id: str,
        installed_server_id: str | None = None,
        agent_id: str | None = None,
    ) -> list[IntegrationPermission]:
        statement = select(IntegrationPermissionModel).where(
            IntegrationPermissionModel.workspace_id == workspace_id
        )
        if installed_server_id:
            statement = statement.where(
                IntegrationPermissionModel.installed_server_id == installed_server_id
            )
        if agent_id:
            statement = statement.where(IntegrationPermissionModel.agent_id == agent_id)
        result = await self._session.execute(
            statement.order_by(IntegrationPermissionModel.priority)
        )
        return [_to_permission(row) for row in result.scalars()]

    async def revoke(self, *, workspace_id: str, permission_id: str) -> bool:
        result = await self._session.execute(
            delete(IntegrationPermissionModel).where(
                IntegrationPermissionModel.id == permission_id,
                IntegrationPermissionModel.workspace_id == workspace_id,
            )
        )
        await self._session.commit()
        return affected(result)

    # --- oauth ------------------------------------------------------------

    async def create_oauth_session(
        self,
        *,
        workspace_id: str,
        installed_server_id: str,
        state: str,
        verifier_ciphertext: bytes,
        wrapped_dek: bytes,
        key_version: str,
        redirect_uri: str,
        requested_scopes: list[str],
        started_by_user_id: str,
        expires_at: datetime,
    ) -> None:
        self._session.add(
            OauthSessionModel(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                installed_server_id=installed_server_id,
                state=state,
                code_verifier_ciphertext=verifier_ciphertext,
                wrapped_dek=wrapped_dek,
                key_version=key_version,
                redirect_uri=redirect_uri,
                requested_scopes=requested_scopes,
                started_by_user_id=started_by_user_id,
                expires_at=expires_at,
                created_at=datetime.now(UTC),
            )
        )
        await self._session.commit()

    async def consume_oauth_session(self, *, state: str) -> dict[str, Any] | None:
        """Reads and deletes atomically.

        `DELETE ... RETURNING` rather than select-then-delete: the pair is
        not atomic, and two concurrent callbacks with the same state
        would both see the row and both proceed. One statement means
        exactly one caller wins.
        """
        result = await self._session.execute(
            delete(OauthSessionModel)
            .where(
                OauthSessionModel.state == state,
                OauthSessionModel.expires_at > datetime.now(UTC),
            )
            .returning(
                OauthSessionModel.workspace_id,
                OauthSessionModel.installed_server_id,
                OauthSessionModel.code_verifier_ciphertext,
                OauthSessionModel.wrapped_dek,
                OauthSessionModel.key_version,
                OauthSessionModel.redirect_uri,
                OauthSessionModel.requested_scopes,
                OauthSessionModel.started_by_user_id,
            )
        )
        row = result.mappings().one_or_none()
        await self._session.commit()
        return dict(row) if row else None

    async def purge_expired_oauth_sessions(self) -> int:
        """An abandoned exchange leaves a live PKCE verifier behind."""
        result = await self._session.execute(
            delete(OauthSessionModel).where(OauthSessionModel.expires_at <= datetime.now(UTC))
        )
        await self._session.commit()
        return getattr(result, "rowcount", 0) or 0

    # --- runtime reads ----------------------------------------------------

    async def list_tool_calls(
        self,
        *,
        workspace_id: str,
        installed_server_id: str | None = None,
        run_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> list[ToolCall]:
        statement = select(ToolCallModel).where(ToolCallModel.workspace_id == workspace_id)
        if installed_server_id:
            statement = statement.where(ToolCallModel.installed_server_id == installed_server_id)
        if run_id:
            statement = statement.where(ToolCallModel.run_id == run_id)
        if status:
            statement = statement.where(ToolCallModel.status == status)
        if cursor:
            # Keyset on `created_at`, which is also the partition key —
            # offset pagination on a fast-appending partitioned table
            # skips and repeats rows as new calls land mid-page.
            statement = statement.where(ToolCallModel.created_at < datetime.fromisoformat(cursor))
        result = await self._session.execute(
            statement.order_by(ToolCallModel.created_at.desc()).limit(limit)
        )
        return [_to_tool_call(row) for row in result.scalars()]

    async def integration_metrics(
        self, *, workspace_id: str, installed_server_id: str | None = None
    ) -> dict[str, Any]:
        conditions = [ToolCallModel.workspace_id == workspace_id]
        if installed_server_id:
            conditions.append(ToolCallModel.installed_server_id == installed_server_id)

        row = (
            (
                await self._session.execute(
                    select(
                        func.count(ToolCallModel.id).label("total"),
                        func.count(ToolCallModel.id)
                        .filter(ToolCallModel.status == ToolCallStatus.SUCCESS)
                        .label("succeeded"),
                        func.count(ToolCallModel.id)
                        .filter(ToolCallModel.status == ToolCallStatus.ERROR)
                        .label("failed"),
                        func.count(ToolCallModel.id)
                        .filter(ToolCallModel.status == ToolCallStatus.DENIED)
                        .label("denied"),
                        func.count(ToolCallModel.id)
                        .filter(ToolCallModel.status == ToolCallStatus.TIMEOUT)
                        .label("timed_out"),
                        func.count(ToolCallModel.id)
                        .filter(ToolCallModel.status == ToolCallStatus.CACHED)
                        .label("cached"),
                        func.coalesce(
                            func.percentile_cont(0.95).within_group(ToolCallModel.duration_ms), 0
                        ).label("p95"),
                        func.coalesce(func.avg(ToolCallModel.duration_ms), 0).label("avg"),
                    ).where(*conditions)
                )
            )
            .mappings()
            .one()
        )

        return {
            "total_calls": int(row["total"]),
            "succeeded_calls": int(row["succeeded"]),
            "failed_calls": int(row["failed"]),
            "denied_calls": int(row["denied"]),
            "timed_out_calls": int(row["timed_out"]),
            "cached_calls": int(row["cached"]),
            # Integers: a latency reported to six decimal places implies a
            # precision the measurement does not have.
            "p95_duration_ms": int(row["p95"] or 0),
            "average_duration_ms": int(row["avg"] or 0),
        }


__all__ = [
    "McpAvailability",
    "SqlIntegrationRepository",
]
