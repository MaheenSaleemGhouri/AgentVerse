"""In-memory `IntegrationRepository` for route tests.

Keyed by workspace throughout, so tenant-isolation assertions are
structurally meaningful — a fake that ignored `workspace_id` would let a
cross-workspace test pass while the real repository leaked.

Like the real one, it has no method that returns a credential value.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from agentverse_api.orchestration_service.domain.integration_entities import (
    AuthScheme,
    CredentialRef,
    HealthStatus,
    InstalledServer,
    InstallStatus,
    IntegrationPermission,
    McpAvailability,
    McpServer,
    McpTransport,
    PermissionLevel,
    ToolCall,
    ToolCallStatus,
)


class FakeIntegrationRepository:
    def __init__(self) -> None:
        self.catalog: dict[str, McpServer] = {}
        self.installed: dict[str, InstalledServer] = {}
        self.credentials: dict[tuple[str, str], CredentialRef] = {}
        #: Ciphertext only. The fake stores what the real table stores,
        #: so a test cannot accidentally assert on a plaintext the real
        #: system never has.
        self.sealed: dict[tuple[str, str], bytes] = {}
        self.permissions: dict[str, IntegrationPermission] = {}
        self.oauth_sessions: dict[str, dict[str, Any]] = {}
        self.tool_calls: list[ToolCall] = []
        self.deleted: set[str] = set()

    # --- catalog ---------------------------------------------------------

    def add_catalog_entry(self, **overrides: Any) -> McpServer:
        entry = McpServer(
            id=overrides.pop("id", str(uuid.uuid4())),
            slug=overrides.pop("slug", "github"),
            name=overrides.pop("name", "GitHub"),
            description=overrides.pop("description", "Read and manage repositories."),
            category=overrides.pop("category", "Developer tools"),
            transport=overrides.pop("transport", McpTransport.STDIO),
            availability=overrides.pop("availability", McpAvailability.OFFICIAL),
            auth_scheme=overrides.pop("auth_scheme", AuthScheme.API_KEY),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            **overrides,
        )
        self.catalog[entry.id] = entry
        return entry

    async def list_catalog(
        self, *, category: str | None = None, query: str | None = None
    ) -> list[McpServer]:
        entries = [e for e in self.catalog.values() if not e.is_deprecated]
        if category:
            entries = [e for e in entries if e.category == category]
        if query:
            needle = query.lower()
            entries = [
                e
                for e in entries
                if needle in e.name.lower()
                or needle in e.description.lower()
                or needle in e.slug.lower()
            ]
        return entries

    async def get_catalog_entry(self, *, server_id: str) -> McpServer | None:
        return self.catalog.get(server_id)

    async def get_catalog_entry_by_slug(self, *, slug: str) -> McpServer | None:
        return next((e for e in self.catalog.values() if e.slug == slug), None)

    async def upsert_catalog_entry(self, *, entry: dict[str, Any]) -> McpServer:
        existing = await self.get_catalog_entry_by_slug(slug=str(entry["slug"]))
        entry_id = existing.id if existing else str(uuid.uuid4())
        server = McpServer(
            id=entry_id,
            slug=str(entry["slug"]),
            name=str(entry["name"]),
            description=str(entry["description"]),
            category=str(entry["category"]),
            transport=McpTransport(entry["transport"]),
            availability=McpAvailability(entry["availability"]),
            auth_scheme=AuthScheme(entry["auth_scheme"]),
            command=entry.get("command"),
            command_args=list(entry.get("command_args") or []),
            endpoint_url=entry.get("endpoint_url"),
            required_credentials=list(entry.get("required_credentials") or []),
            oauth_scopes=list(entry.get("oauth_scopes") or []),
            documentation_url=entry.get("documentation_url"),
            icon_slug=entry.get("icon_slug"),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.catalog[entry_id] = server
        return server

    # --- installations ---------------------------------------------------

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
        server = InstalledServer(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            mcp_server_id=mcp_server_id,
            display_name=display_name,
            transport=McpTransport(transport),
            endpoint_url=endpoint_url,
            status=status,
            health=HealthStatus.UNKNOWN,
            config=config,
            installed_by_user_id=installed_by_user_id,
            created_at=now,
            updated_at=now,
        )
        self.installed[server.id] = server
        return server

    async def list_installed(self, *, workspace_id: str) -> list[InstalledServer]:
        return [
            s
            for s in self.installed.values()
            if s.workspace_id == workspace_id and s.id not in self.deleted
        ]

    async def get_installed(
        self, *, workspace_id: str, installed_server_id: str
    ) -> InstalledServer | None:
        server = self.installed.get(installed_server_id)
        if (
            server is None
            or server.workspace_id != workspace_id
            or installed_server_id in self.deleted
        ):
            return None
        return server

    async def update_installed(
        self, *, workspace_id: str, installed_server_id: str, changes: dict[str, Any]
    ) -> InstalledServer | None:
        server = await self.get_installed(
            workspace_id=workspace_id, installed_server_id=installed_server_id
        )
        if server is None:
            return None
        fields = {
            name: getattr(server, name)
            for name in (
                "id",
                "workspace_id",
                "mcp_server_id",
                "display_name",
                "transport",
                "endpoint_url",
                "status",
                "health",
                "config",
                "discovered_tools",
                "tools_discovered_at",
                "last_health_check_at",
                "last_error",
                "version",
                "installed_by_user_id",
                "created_at",
            )
        }
        updated = InstalledServer(**{**fields, **changes, "updated_at": datetime.now(UTC)})
        self.installed[installed_server_id] = updated
        return updated

    async def uninstall(self, *, workspace_id: str, installed_server_id: str) -> bool:
        if (
            await self.get_installed(
                workspace_id=workspace_id, installed_server_id=installed_server_id
            )
            is None
        ):
            return False
        self.deleted.add(installed_server_id)
        return True

    async def record_discovery(self, **kwargs: Any) -> None:
        return None

    # --- credentials -----------------------------------------------------

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
        ref = CredentialRef(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            installed_server_id=installed_server_id,
            key=key,
            auth_scheme=auth_scheme,
            hint=hint,
            expires_at=expires_at,
            last_rotated_at=now,
            created_at=now,
        )
        self.credentials[(installed_server_id, key)] = ref
        self.sealed[(installed_server_id, key)] = ciphertext
        return ref

    async def list_credential_refs(
        self, *, workspace_id: str, installed_server_id: str
    ) -> list[CredentialRef]:
        return [
            ref
            for (server_id, _), ref in self.credentials.items()
            if server_id == installed_server_id and ref.workspace_id == workspace_id
        ]

    async def delete_credential(
        self, *, workspace_id: str, installed_server_id: str, key: str
    ) -> bool:
        ref = self.credentials.get((installed_server_id, key))
        if ref is None or ref.workspace_id != workspace_id:
            return False
        del self.credentials[(installed_server_id, key)]
        self.sealed.pop((installed_server_id, key), None)
        return True

    # --- permissions -----------------------------------------------------

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
        permission = IntegrationPermission(
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
            created_at=datetime.now(UTC),
        )
        self.permissions[permission.id] = permission
        return permission

    async def list_grants(
        self,
        *,
        workspace_id: str,
        installed_server_id: str | None = None,
        agent_id: str | None = None,
    ) -> list[IntegrationPermission]:
        grants = [p for p in self.permissions.values() if p.workspace_id == workspace_id]
        if installed_server_id:
            grants = [p for p in grants if p.installed_server_id == installed_server_id]
        if agent_id:
            grants = [p for p in grants if p.agent_id == agent_id]
        return grants

    async def revoke(self, *, workspace_id: str, permission_id: str) -> bool:
        permission = self.permissions.get(permission_id)
        if permission is None or permission.workspace_id != workspace_id:
            return False
        del self.permissions[permission_id]
        return True

    # --- oauth -----------------------------------------------------------

    async def create_oauth_session(
        self, *, state: str, verifier_ciphertext: bytes, expires_at: datetime, **kwargs: Any
    ) -> None:
        # Keyed exactly as `SqlIntegrationRepository.consume_oauth_session`
        # returns it (`code_verifier_ciphertext`, not the port parameter's
        # `verifier_ciphertext`) — a fake with a different shape than the
        # real repository would let a test pass here and break against
        # real Postgres, which is the false-confidence failure mode
        # fakes exist to prevent.
        self.oauth_sessions[state] = {
            "state": state,
            "code_verifier_ciphertext": verifier_ciphertext,
            "expires_at": expires_at,
            **kwargs,
        }

    async def consume_oauth_session(self, *, state: str) -> dict[str, Any] | None:
        session = self.oauth_sessions.get(state)
        if session is None:
            return None
        if session["expires_at"] <= datetime.now(UTC):
            return None
        return self.oauth_sessions.pop(state)

    async def purge_expired_oauth_sessions(self) -> int:
        expired = [s for s, session in self.oauth_sessions.items() if session["expires_at"] <= datetime.now(UTC)]
        for s in expired:
            del self.oauth_sessions[s]
        return len(expired)

    # --- runtime ---------------------------------------------------------

    def add_tool_call(self, **overrides: Any) -> ToolCall:
        call = ToolCall(
            id=overrides.pop("id", str(uuid.uuid4())),
            workspace_id=overrides.pop("workspace_id", "ws-1"),
            run_id=overrides.pop("run_id", None),
            team_session_id=overrides.pop("team_session_id", None),
            agent_id=overrides.pop("agent_id", None),
            installed_server_id=overrides.pop("installed_server_id", None),
            tool_name=overrides.pop("tool_name", "list_issues"),
            status=overrides.pop("status", ToolCallStatus.SUCCESS),
            arguments=overrides.pop("arguments", {}),
            result_preview=overrides.pop("result_preview", None),
            result_bytes=overrides.pop("result_bytes", None),
            duration_ms=overrides.pop("duration_ms", 100),
            error_message=overrides.pop("error_message", None),
            denial_reason=overrides.pop("denial_reason", None),
            attempt=overrides.pop("attempt", 1),
            created_at=overrides.pop("created_at", datetime.now(UTC)),
        )
        self.tool_calls.append(call)
        return call

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
        calls = [c for c in self.tool_calls if c.workspace_id == workspace_id]
        if installed_server_id:
            calls = [c for c in calls if c.installed_server_id == installed_server_id]
        if run_id:
            calls = [c for c in calls if c.run_id == run_id]
        if status:
            calls = [c for c in calls if c.status.value == status]
        calls.sort(key=lambda c: c.created_at, reverse=True)
        if cursor:
            boundary = datetime.fromisoformat(cursor)
            calls = [c for c in calls if c.created_at < boundary]
        return calls[:limit]

    async def integration_metrics(
        self, *, workspace_id: str, installed_server_id: str | None = None
    ) -> dict[str, Any]:
        calls = [c for c in self.tool_calls if c.workspace_id == workspace_id]
        if installed_server_id:
            calls = [c for c in calls if c.installed_server_id == installed_server_id]

        def _count(status: ToolCallStatus) -> int:
            return sum(1 for c in calls if c.status is status)

        durations = [c.duration_ms for c in calls if c.duration_ms is not None]
        return {
            "total_calls": len(calls),
            "succeeded_calls": _count(ToolCallStatus.SUCCESS),
            "failed_calls": _count(ToolCallStatus.ERROR),
            "denied_calls": _count(ToolCallStatus.DENIED),
            "timed_out_calls": _count(ToolCallStatus.TIMEOUT),
            "cached_calls": _count(ToolCallStatus.CACHED),
            "p95_duration_ms": int(max(durations)) if durations else 0,
            "average_duration_ms": int(sum(durations) / len(durations)) if durations else 0,
        }
