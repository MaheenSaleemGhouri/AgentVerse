"""`/api/v1/workspaces/{workspace_id}/integrations` — the MCP
marketplace, installations, credentials, permissions, and runtime reads.

`workspace_id` always comes from the authenticated `WorkspaceContext`,
never the path parameter (Rule 6). The path segment exists for URL shape
and is validated by the same role dependency.

**Role choices are deliberate and not uniform.** Installing a server and
writing a credential are `admin`: an install decides which third party an
agent may reach, and a credential is a key to a customer's own GitHub or
Slack. Browsing the catalog and reading logs are `viewer`. Granting a
server to an agent is `member`, because a builder configuring their own
agent should not need an admin every time — the *set* of reachable
servers is already admin-gated, so a member can only grant from what an
admin has already approved.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from agentverse_shared.security.envelope import CredentialVault, credential_aad, hint_for
from fastapi import APIRouter, Depends, HTTPException, Query, status

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_admin,
    require_member,
    require_viewer,
)
from agentverse_api.orchestration_service.domain.integration_entities import (
    AuthScheme,
    CredentialRef,
    InstalledServer,
    InstallStatus,
    IntegrationPermission,
    McpAvailability,
    McpServer,
    PermissionLevel,
    ToolCall,
)
from agentverse_api.orchestration_service.domain.ports.integration_repository import (
    IntegrationRepository,
)
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_credential_vault,
    get_integration_repository,
)
from agentverse_api.orchestration_service.interface.schemas.integrations import (
    CredentialResponse,
    GrantPermissionRequest,
    InstalledServerResponse,
    InstallFromCatalogRequest,
    IntegrationMetricsResponse,
    McpServerResponse,
    PermissionResponse,
    PutCredentialRequest,
    RegisterCustomServerRequest,
    ToolCallPage,
    ToolCallResponse,
    ToolSummary,
    UpdateInstalledServerRequest,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/integrations", tags=["integrations"])

#: How long an in-flight OAuth exchange stays valid. Short because the
#: row holds a live PKCE verifier — an exchange that has not completed in
#: ten minutes is abandoned, and the row is a secret with no purpose.
OAUTH_SESSION_TTL = timedelta(minutes=10)

MAX_PAGE_SIZE = 200


def _catalog_response(entry: McpServer) -> McpServerResponse:
    return McpServerResponse(
        id=entry.id,
        slug=entry.slug,
        name=entry.name,
        description=entry.description,
        category=entry.category,
        transport=entry.transport.value,
        availability=entry.availability.value,
        auth_scheme=entry.auth_scheme.value,
        required_credentials=entry.required_credentials,
        oauth_scopes=entry.oauth_scopes,
        documentation_url=entry.documentation_url,
        icon_slug=entry.icon_slug,
        is_installable=entry.is_installable,
    )


def _installed_response(server: InstalledServer) -> InstalledServerResponse:
    return InstalledServerResponse(
        id=server.id,
        workspace_id=server.workspace_id,
        mcp_server_id=server.mcp_server_id,
        display_name=server.display_name,
        transport=server.transport.value,
        endpoint_url=server.endpoint_url,
        status=server.status.value,
        health=server.health.value,
        tools=[
            ToolSummary(name=tool.name, description=tool.description, is_mutating=tool.is_mutating)
            for tool in server.discovered_tools
        ],
        tools_discovered_at=server.tools_discovered_at,
        last_health_check_at=server.last_health_check_at,
        last_error=server.last_error,
        version=server.version,
        created_at=server.created_at,
        updated_at=server.updated_at,
    )


def _credential_response(ref: CredentialRef) -> CredentialResponse:
    return CredentialResponse(
        id=ref.id,
        installed_server_id=ref.installed_server_id,
        key=ref.key,
        auth_scheme=ref.auth_scheme.value,
        hint=ref.hint,
        expires_at=ref.expires_at,
        last_rotated_at=ref.last_rotated_at,
        created_at=ref.created_at,
    )


def _permission_response(grant: IntegrationPermission) -> PermissionResponse:
    return PermissionResponse(
        id=grant.id,
        installed_server_id=grant.installed_server_id,
        agent_id=grant.agent_id,
        team_id=grant.team_id,
        level=grant.level.value,
        allowed_tools=grant.allowed_tools,
        timeout_seconds=grant.timeout_seconds,
        max_retries=grant.max_retries,
        cache_ttl_seconds=grant.cache_ttl_seconds,
        max_calls_per_run=grant.max_calls_per_run,
        priority=grant.priority,
        created_at=grant.created_at,
    )


def _tool_call_response(call: ToolCall) -> ToolCallResponse:
    return ToolCallResponse(
        id=call.id,
        run_id=call.run_id,
        agent_id=call.agent_id,
        installed_server_id=call.installed_server_id,
        tool_name=call.tool_name,
        status=call.status.value,
        arguments=call.arguments,
        result_preview=call.result_preview,
        result_bytes=call.result_bytes,
        duration_ms=call.duration_ms,
        error_message=call.error_message,
        denial_reason=call.denial_reason,
        attempt=call.attempt,
        created_at=call.created_at,
    )


async def _require_installed(
    repo: IntegrationRepository, context: WorkspaceContext, installed_server_id: str
) -> InstalledServer:
    """404 across workspaces, never 403.

    A 403 would confirm the installation exists, which leaks another
    tenant's integrations by inference (CLAUDE.md §10).
    """
    server = await repo.get_installed(
        workspace_id=context.workspace_id, installed_server_id=installed_server_id
    )
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    return server


# --- marketplace ----------------------------------------------------------


@router.get("/catalog", response_model=list[McpServerResponse])
async def list_catalog_route(
    category: str | None = Query(default=None, max_length=100),
    q: str | None = Query(default=None, max_length=200),
    context: WorkspaceContext = Depends(require_viewer),
    repo: IntegrationRepository = Depends(get_integration_repository),
) -> list[McpServerResponse]:
    """The marketplace.

    Still workspace-authenticated even though the catalog is
    platform-wide: browsing it reveals what the platform integrates with,
    which is not information for anonymous callers.
    """
    del context  # auth only; the catalog is not tenant-scoped
    entries = await repo.list_catalog(category=category, query=q)
    return [_catalog_response(entry) for entry in entries]


# --- installations --------------------------------------------------------


@router.post("", response_model=InstalledServerResponse, status_code=201)
async def install_from_catalog_route(
    body: InstallFromCatalogRequest,
    context: WorkspaceContext = Depends(require_admin),
    repo: IntegrationRepository = Depends(get_integration_repository),
) -> InstalledServerResponse:
    """Installs a vetted catalog entry.

    Admin-gated: an install decides which third party the workspace's
    agents may reach, and its command (for stdio) runs on the worker
    fleet.
    """
    entry = await repo.get_catalog_entry(server_id=body.mcp_server_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Catalog entry not found")
    if not entry.is_installable:
        # The honest refusal: no MCP server exists for this service, so
        # installing it would create a connection that can never succeed.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{entry.name} has no installable MCP server yet. Register your own "
                "endpoint as a custom server instead."
            ),
        )

    # OAuth servers are not usable until the flow completes; anything
    # else needing a credential is not usable until one is written. Both
    # start `pending_auth` so the UI can say what is missing rather than
    # showing an active integration that fails on first use.
    needs_setup = entry.auth_scheme is not AuthScheme.NONE
    server = await repo.install(
        workspace_id=context.workspace_id,
        mcp_server_id=entry.id,
        display_name=body.display_name or entry.name,
        transport=entry.transport.value,
        # Null: a catalog install reads its endpoint from the catalog at
        # connect time, so a later catalog fix reaches existing installs.
        endpoint_url=None,
        config=body.config,
        status=InstallStatus.PENDING_AUTH if needs_setup else InstallStatus.ACTIVE,
        installed_by_user_id=context.user_id,
    )
    return _installed_response(server)


@router.post("/custom", response_model=InstalledServerResponse, status_code=201)
async def register_custom_server_route(
    body: RegisterCustomServerRequest,
    context: WorkspaceContext = Depends(require_admin),
    repo: IntegrationRepository = Depends(get_integration_repository),
) -> InstalledServerResponse:
    """Registers a user's own MCP endpoint.

    `mcp_server_id` is null, which is what marks this as custom — and
    what makes `factory._build_stdio` refuse it, since stdio is available
    only to vetted catalog entries.
    """
    server = await repo.install(
        workspace_id=context.workspace_id,
        mcp_server_id=None,
        display_name=body.display_name,
        transport=body.transport,
        endpoint_url=body.endpoint_url,
        config=body.config,
        status=(InstallStatus.PENDING_AUTH if body.auth_scheme != "none" else InstallStatus.ACTIVE),
        installed_by_user_id=context.user_id,
    )
    return _installed_response(server)


@router.get("", response_model=list[InstalledServerResponse])
async def list_installed_route(
    context: WorkspaceContext = Depends(require_viewer),
    repo: IntegrationRepository = Depends(get_integration_repository),
) -> list[InstalledServerResponse]:
    servers = await repo.list_installed(workspace_id=context.workspace_id)
    return [_installed_response(server) for server in servers]


@router.get("/{installed_server_id}", response_model=InstalledServerResponse)
async def get_installed_route(
    installed_server_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    repo: IntegrationRepository = Depends(get_integration_repository),
) -> InstalledServerResponse:
    return _installed_response(await _require_installed(repo, context, installed_server_id))


@router.patch("/{installed_server_id}", response_model=InstalledServerResponse)
async def update_installed_route(
    installed_server_id: str,
    body: UpdateInstalledServerRequest,
    context: WorkspaceContext = Depends(require_admin),
    repo: IntegrationRepository = Depends(get_integration_repository),
) -> InstalledServerResponse:
    await _require_installed(repo, context, installed_server_id)
    changes: dict[str, Any] = body.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] is not None:
        changes["status"] = InstallStatus(changes["status"])
    updated = await repo.update_installed(
        workspace_id=context.workspace_id,
        installed_server_id=installed_server_id,
        changes=changes,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    return _installed_response(updated)


@router.delete("/{installed_server_id}", status_code=204, response_model=None)
async def uninstall_route(
    installed_server_id: str,
    context: WorkspaceContext = Depends(require_admin),
    repo: IntegrationRepository = Depends(get_integration_repository),
) -> None:
    """Soft delete. The server's `tool_calls` history stays readable —
    that history is the audit trail, and losing it because someone
    removed the integration defeats its purpose.
    """
    if not await repo.uninstall(
        workspace_id=context.workspace_id, installed_server_id=installed_server_id
    ):
        raise HTTPException(status_code=404, detail="Integration not found")


# --- credentials (write-only) ---------------------------------------------


@router.put(
    "/{installed_server_id}/credentials", response_model=CredentialResponse, status_code=201
)
async def put_credential_route(
    installed_server_id: str,
    body: PutCredentialRequest,
    context: WorkspaceContext = Depends(require_admin),
    repo: IntegrationRepository = Depends(get_integration_repository),
    vault: CredentialVault = Depends(get_credential_vault),
) -> CredentialResponse:
    """Writes or rotates a credential.

    The value is encrypted here and never stored, logged, or returned in
    plaintext. The AAD binds the ciphertext to this
    `(workspace, server, key)` — a row copied into another workspace
    fails to decrypt rather than handing over a working credential.
    """
    await _require_installed(repo, context, installed_server_id)

    sealed = vault.seal(
        body.value,
        associated_data=credential_aad(
            workspace_id=context.workspace_id,
            installed_server_id=installed_server_id,
            key=body.key,
        ),
    )
    ref = await repo.put_credential(
        workspace_id=context.workspace_id,
        installed_server_id=installed_server_id,
        key=body.key,
        auth_scheme=AuthScheme(body.auth_scheme),
        ciphertext=sealed.ciphertext,
        wrapped_dek=sealed.wrapped_dek,
        key_version=sealed.key_version,
        hint=hint_for(body.value),
        expires_at=body.expires_at,
    )

    # A server waiting on a credential becomes usable once it has one.
    # Done here rather than making the admin flip a switch afterwards:
    # the reason it was pending is now resolved.
    server = await repo.get_installed(
        workspace_id=context.workspace_id, installed_server_id=installed_server_id
    )
    if server is not None and server.status is InstallStatus.PENDING_AUTH:
        await repo.update_installed(
            workspace_id=context.workspace_id,
            installed_server_id=installed_server_id,
            changes={"status": InstallStatus.ACTIVE},
        )

    return _credential_response(ref)


@router.get("/{installed_server_id}/credentials", response_model=list[CredentialResponse])
async def list_credentials_route(
    installed_server_id: str,
    context: WorkspaceContext = Depends(require_admin),
    repo: IntegrationRepository = Depends(get_integration_repository),
) -> list[CredentialResponse]:
    """Which credentials exist, and when they were last rotated.

    Never their values — `CredentialResponse` has no field for one. There
    is deliberately no `GET /{key}/value` route: building the read path
    at all is what later gets loosened.
    """
    await _require_installed(repo, context, installed_server_id)
    refs = await repo.list_credential_refs(
        workspace_id=context.workspace_id, installed_server_id=installed_server_id
    )
    return [_credential_response(ref) for ref in refs]


@router.delete("/{installed_server_id}/credentials/{key}", status_code=204, response_model=None)
async def delete_credential_route(
    installed_server_id: str,
    key: str,
    context: WorkspaceContext = Depends(require_admin),
    repo: IntegrationRepository = Depends(get_integration_repository),
) -> None:
    await _require_installed(repo, context, installed_server_id)
    if not await repo.delete_credential(
        workspace_id=context.workspace_id, installed_server_id=installed_server_id, key=key
    ):
        raise HTTPException(status_code=404, detail="Credential not found")


# --- permissions ----------------------------------------------------------


@router.post(
    "/{installed_server_id}/permissions", response_model=PermissionResponse, status_code=201
)
async def grant_permission_route(
    installed_server_id: str,
    body: GrantPermissionRequest,
    context: WorkspaceContext = Depends(require_member),
    repo: IntegrationRepository = Depends(get_integration_repository),
) -> PermissionResponse:
    """Grants a server's tools to an agent, a team, or the workspace.

    `member` rather than `admin`: the *set* of reachable servers is
    already admin-gated at install, so a member can only grant from what
    an admin approved. Requiring an admin for every agent's tool list
    would make the feature unusable without loosening the gate that
    actually matters.
    """
    await _require_installed(repo, context, installed_server_id)
    grant = await repo.grant(
        workspace_id=context.workspace_id,
        installed_server_id=installed_server_id,
        agent_id=body.agent_id,
        team_id=body.team_id,
        level=PermissionLevel(body.level),
        allowed_tools=body.allowed_tools,
        limits={
            "timeout_seconds": body.timeout_seconds,
            "max_retries": body.max_retries,
            "cache_ttl_seconds": body.cache_ttl_seconds,
            "max_calls_per_run": body.max_calls_per_run,
            "priority": body.priority,
        },
        granted_by_user_id=context.user_id,
    )
    return _permission_response(grant)


@router.get("/{installed_server_id}/permissions", response_model=list[PermissionResponse])
async def list_permissions_route(
    installed_server_id: str,
    agent_id: str | None = Query(default=None, max_length=64),
    context: WorkspaceContext = Depends(require_viewer),
    repo: IntegrationRepository = Depends(get_integration_repository),
) -> list[PermissionResponse]:
    await _require_installed(repo, context, installed_server_id)
    grants = await repo.list_grants(
        workspace_id=context.workspace_id,
        installed_server_id=installed_server_id,
        agent_id=agent_id,
    )
    return [_permission_response(grant) for grant in grants]


@router.delete(
    "/{installed_server_id}/permissions/{permission_id}", status_code=204, response_model=None
)
async def revoke_permission_route(
    installed_server_id: str,
    permission_id: str,
    context: WorkspaceContext = Depends(require_member),
    repo: IntegrationRepository = Depends(get_integration_repository),
) -> None:
    await _require_installed(repo, context, installed_server_id)
    if not await repo.revoke(workspace_id=context.workspace_id, permission_id=permission_id):
        raise HTTPException(status_code=404, detail="Permission not found")


# --- runtime reads --------------------------------------------------------


@router.get("/runtime/calls", response_model=ToolCallPage)
async def list_tool_calls_route(
    installed_server_id: str | None = Query(default=None, max_length=64),
    run_id: str | None = Query(default=None, max_length=64),
    call_status: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None),
    context: WorkspaceContext = Depends(require_viewer),
    repo: IntegrationRepository = Depends(get_integration_repository),
) -> ToolCallPage:
    """Execution history, including denied and blocked calls.

    Cursor-paginated on `created_at`, which is also the partition key —
    offset pagination on a fast-appending partitioned table skips and
    repeats rows as new calls land mid-page (CLAUDE.md §7).
    """
    rows = await repo.list_tool_calls(
        workspace_id=context.workspace_id,
        installed_server_id=installed_server_id,
        run_id=run_id,
        status=call_status,
        limit=limit + 1,
        cursor=cursor,
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return ToolCallPage(
        data=[_tool_call_response(call) for call in page],
        next_cursor=page[-1].created_at.isoformat() if has_more and page else None,
        has_more=has_more,
    )


@router.get("/runtime/metrics", response_model=IntegrationMetricsResponse)
async def integration_metrics_route(
    installed_server_id: str | None = Query(default=None, max_length=64),
    context: WorkspaceContext = Depends(require_viewer),
    repo: IntegrationRepository = Depends(get_integration_repository),
) -> IntegrationMetricsResponse:
    return IntegrationMetricsResponse(
        **await repo.integration_metrics(
            workspace_id=context.workspace_id, installed_server_id=installed_server_id
        )
    )


def generate_oauth_state() -> str:
    """A CSRF token for the authorization-code flow.

    `token_urlsafe(32)` — 256 bits from a CSPRNG. The state is the only
    thing tying a callback to the session that started it, so a guessable
    one would let an attacker complete someone else's flow.
    """
    return secrets.token_urlsafe(32)


def oauth_session_expiry(now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)) + OAUTH_SESSION_TTL


__all__ = [
    "McpAvailability",
    "generate_oauth_state",
    "oauth_session_expiry",
    "router",
]
