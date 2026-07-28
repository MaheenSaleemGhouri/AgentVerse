"""Repository port for the MCP integration tables.

Every method that touches tenant data takes `workspace_id` as a required
keyword (Rule 11). The catalog methods deliberately do not — `mcp_servers`
is platform-wide, and the exemption is recorded in ADR-0010 rather than
left to look like an omission.

**There is no method that returns a credential value.** Not masked, not
partial. `CredentialRef` carries a four-character hint and nothing else.
Building the read path at all is what later gets loosened, so it does not
exist to loosen.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from agentverse_api.orchestration_service.domain.integration_entities import (
    AuthScheme,
    CredentialRef,
    HealthStatus,
    InstalledServer,
    InstallStatus,
    IntegrationPermission,
    McpServer,
    PermissionLevel,
    ToolCall,
)


class IntegrationRepository(Protocol):
    # --- catalog (platform-wide, not tenant-scoped) ----------------------

    async def list_catalog(
        self, *, category: str | None = None, query: str | None = None
    ) -> list[McpServer]: ...

    async def get_catalog_entry(self, *, server_id: str) -> McpServer | None: ...

    async def get_catalog_entry_by_slug(self, *, slug: str) -> McpServer | None: ...

    async def upsert_catalog_entry(self, *, entry: dict[str, Any]) -> McpServer:
        """Idempotent seeding by `slug`.

        Upsert rather than insert so re-running the seed after editing a
        description updates the row instead of failing on the unique
        constraint — a seed that can only run once is a seed nobody runs.
        """
        ...

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
    ) -> InstalledServer: ...

    async def list_installed(self, *, workspace_id: str) -> list[InstalledServer]: ...

    async def get_installed(
        self, *, workspace_id: str, installed_server_id: str
    ) -> InstalledServer | None: ...

    async def update_installed(
        self, *, workspace_id: str, installed_server_id: str, changes: dict[str, Any]
    ) -> InstalledServer | None: ...

    async def uninstall(self, *, workspace_id: str, installed_server_id: str) -> bool:
        """Soft delete. An uninstalled server's `tool_calls` history must
        stay readable — that history is the audit trail, and losing it
        because someone removed the integration defeats the point.
        """
        ...

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
        """Writes the discovered surface and appends a `server_versions`
        row when it changed, so a breaking schema change is visible after
        the fact rather than a silent runtime failure.
        """
        ...

    # --- credentials (write-only by design) -------------------------------

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
        """Creates or rotates. One method for both because a rotation is
        a write of the same shape, and a separate `rotate` would be a
        second path to keep correct.
        """
        ...

    async def list_credential_refs(
        self, *, workspace_id: str, installed_server_id: str
    ) -> list[CredentialRef]:
        """Metadata only — which keys exist, when they were rotated. The
        return type has no field for a value.
        """
        ...

    async def delete_credential(
        self, *, workspace_id: str, installed_server_id: str, key: str
    ) -> bool: ...

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
    ) -> IntegrationPermission: ...

    async def list_grants(
        self,
        *,
        workspace_id: str,
        installed_server_id: str | None = None,
        agent_id: str | None = None,
    ) -> list[IntegrationPermission]: ...

    async def revoke(self, *, workspace_id: str, permission_id: str) -> bool: ...

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
    ) -> None: ...

    async def consume_oauth_session(self, *, state: str) -> dict[str, Any] | None:
        """Reads and **deletes** in one step.

        Deleted rather than marked used: the PKCE verifier is itself a
        credential, and a consumed row is a live secret with no remaining
        purpose. Single-use also means a replayed callback finds nothing.

        Deliberately not workspace-scoped — the caller does not know the
        workspace yet; `state` is the only thing the provider echoes back,
        and it is unique and unguessable. The returned row carries the
        workspace, which every subsequent operation is then scoped by.
        """
        ...

    async def purge_expired_oauth_sessions(self) -> int: ...

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
    ) -> list[ToolCall]: ...

    async def integration_metrics(
        self, *, workspace_id: str, installed_server_id: str | None = None
    ) -> dict[str, Any]:
        """Aggregates over `tool_calls`.

        Computed in Postgres rather than by loading rows and summing in
        Python: the table is partitioned and high-volume, and a p95 over
        it per dashboard load is a scan nobody needs.
        """
        ...
