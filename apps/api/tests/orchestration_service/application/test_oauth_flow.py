"""`OAuthFlowService` — the piece that completes what the Phase 6
scaffolding left half-built (`docs/PHASE-6-MCP-CHECKLIST.md` gap #1).

`oauth_sessions`, the repository methods, and `OauthStartResponse` all
predate this file; these tests exercise the actual authorize-URL
construction and code-for-token exchange that never existed before.

The provider's token endpoint is a `httpx.MockTransport`, never a real
network call — these are unit tests of AgentVerse's own logic, not of
Notion's API, and a real call would make the suite flaky and slow for no
added coverage (CLAUDE.md §11: LLM/vector-DB-style externals are faked;
the same principle applies to any third-party network dependency).
"""

from __future__ import annotations

import base64
import os
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from agentverse_shared.security.envelope import CredentialVault, KeyRing

from agentverse_api.orchestration_service.application.oauth_flow import (
    ACCESS_TOKEN_KEY,
    REFRESH_TOKEN_KEY,
    OAuthFlowError,
    OAuthFlowService,
)
from agentverse_api.orchestration_service.domain.integration_entities import (
    AuthScheme,
    InstallStatus,
)
from agentverse_api.orchestration_service.infrastructure.oauth.providers import (
    OAuthProviderConfig,
)
from tests.fakes.integration_repository import FakeIntegrationRepository

CALLBACK_URL = "http://localhost:8000/api/v1/integrations/oauth/callback"
WORKSPACE_ID = "ws-1"

NOTION_PROVIDER = OAuthProviderConfig(
    slug="notion",
    authorize_url="https://api.notion.com/v1/oauth/authorize",
    token_url="https://api.notion.com/v1/oauth/token",
    client_id="test-client-id",
    client_secret="test-client-secret",
)


def _vault() -> CredentialVault:
    return CredentialVault(
        KeyRing.from_env(
            {"AGENTVERSE_CREDENTIAL_KEK_V1": base64.b64encode(os.urandom(32)).decode()},
            active_version="v1",
        )
    )


def _service(
    *,
    repo: FakeIntegrationRepository,
    transport: httpx.MockTransport | None = None,
    providers: dict[str, OAuthProviderConfig] | None = None,
) -> OAuthFlowService:
    return OAuthFlowService(
        repo=repo,
        vault=_vault(),
        providers=providers if providers is not None else {"notion": NOTION_PROVIDER},
        callback_url=CALLBACK_URL,
        http_client=httpx.AsyncClient(transport=transport) if transport else httpx.AsyncClient(),
    )


async def _install_notion(repo: FakeIntegrationRepository) -> str:
    entry = repo.add_catalog_entry(
        slug="notion",
        name="Notion",
        auth_scheme=AuthScheme.OAUTH2,
        oauth_scopes=["read_content"],
    )
    server = await repo.install(
        workspace_id=WORKSPACE_ID,
        mcp_server_id=entry.id,
        display_name="Notion",
        transport=entry.transport,
        endpoint_url=None,
        config={},
        status=InstallStatus.PENDING_AUTH,
        installed_by_user_id="user-1",
    )
    return str(server.id)


class TestStart:
    async def test_builds_a_pkce_authorization_url_and_records_the_session(self) -> None:
        repo = FakeIntegrationRepository()
        installed = await _install_notion(repo)
        service = _service(repo=repo)

        result = await service.start(
            workspace_id=WORKSPACE_ID, installed_server_id=installed, user_id="user-1"
        )

        parsed = urlparse(result.authorization_url)
        assert parsed.netloc == "api.notion.com"
        query = parse_qs(parsed.query)
        assert query["client_id"] == [NOTION_PROVIDER.client_id]
        assert query["redirect_uri"] == [CALLBACK_URL]
        assert query["response_type"] == ["code"]
        assert query["code_challenge_method"] == ["S256"]
        assert query["state"] == [result.state]
        # The verifier itself must never appear in the URL — only its
        # S256 challenge does. A leaked verifier defeats PKCE entirely.
        assert "code_verifier" not in query
        assert query["scope"] == ["read_content"]

        session = repo.oauth_sessions[result.state]
        assert session["workspace_id"] == WORKSPACE_ID
        assert session["installed_server_id"] == installed

    async def test_two_starts_for_the_same_install_produce_different_states(self) -> None:
        repo = FakeIntegrationRepository()
        installed = await _install_notion(repo)
        service = _service(repo=repo)

        first = await service.start(
            workspace_id=WORKSPACE_ID, installed_server_id=installed, user_id="user-1"
        )
        second = await service.start(
            workspace_id=WORKSPACE_ID, installed_server_id=installed, user_id="user-1"
        )

        assert first.state != second.state
        # Both sessions coexist — completing the first must not silently
        # invalidate an attempt still in flight in another tab.
        assert first.state in repo.oauth_sessions
        assert second.state in repo.oauth_sessions

    async def test_refuses_a_custom_server_with_no_catalog_entry(self) -> None:
        repo = FakeIntegrationRepository()
        server = await repo.install(
            workspace_id=WORKSPACE_ID,
            mcp_server_id=None,
            display_name="My internal API",
            transport="streamable_http",
            endpoint_url="https://internal.example.invalid/mcp",
            config={},
            status=InstallStatus.PENDING_AUTH,
            installed_by_user_id="user-1",
        )
        service = _service(repo=repo)

        with pytest.raises(OAuthFlowError, match="Custom servers"):
            await service.start(
                workspace_id=WORKSPACE_ID, installed_server_id=str(server.id), user_id="user-1"
            )

    async def test_refuses_a_provider_with_no_registered_credentials(self) -> None:
        repo = FakeIntegrationRepository()
        installed = await _install_notion(repo)
        # No providers configured at all — mirrors a deployment that has
        # not registered a Notion OAuth app.
        service = _service(repo=repo, providers={})

        with pytest.raises(OAuthFlowError, match="not configured"):
            await service.start(
                workspace_id=WORKSPACE_ID, installed_server_id=installed, user_id="user-1"
            )

    async def test_refuses_a_non_oauth_catalog_entry(self) -> None:
        repo = FakeIntegrationRepository()
        entry = repo.add_catalog_entry(slug="github", auth_scheme=AuthScheme.API_KEY)
        server = await repo.install(
            workspace_id=WORKSPACE_ID,
            mcp_server_id=entry.id,
            display_name="GitHub",
            transport=entry.transport,
            endpoint_url=None,
            config={},
            status=InstallStatus.PENDING_AUTH,
            installed_by_user_id="user-1",
        )
        service = _service(repo=repo)

        with pytest.raises(OAuthFlowError, match="does not use OAuth"):
            await service.start(
                workspace_id=WORKSPACE_ID, installed_server_id=str(server.id), user_id="user-1"
            )


def _token_transport(payload: dict[str, object], *, status_code: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return httpx.MockTransport(handler)


class TestHandleCallback:
    async def test_exchanges_the_code_stores_the_token_and_activates_the_server(self) -> None:
        repo = FakeIntegrationRepository()
        installed = await _install_notion(repo)
        transport = _token_transport({"access_token": "secret-access-token", "refresh_token": "r1"})
        service = _service(repo=repo, transport=transport)

        start = await service.start(
            workspace_id=WORKSPACE_ID, installed_server_id=installed, user_id="user-1"
        )
        workspace_id, installed_server_id = await service.handle_callback(
            state=start.state, code="auth-code-123"
        )

        assert workspace_id == WORKSPACE_ID
        assert installed_server_id == installed

        server = repo.installed[installed]
        assert server.status is InstallStatus.ACTIVE

        stored_keys = {key for (server_id, key) in repo.credentials if server_id == installed}
        assert ACCESS_TOKEN_KEY in stored_keys
        assert REFRESH_TOKEN_KEY in stored_keys

    async def test_a_replayed_callback_is_refused(self) -> None:
        repo = FakeIntegrationRepository()
        installed = await _install_notion(repo)
        transport = _token_transport({"access_token": "secret-access-token"})
        service = _service(repo=repo, transport=transport)

        start = await service.start(
            workspace_id=WORKSPACE_ID, installed_server_id=installed, user_id="user-1"
        )
        await service.handle_callback(state=start.state, code="auth-code-123")

        with pytest.raises(OAuthFlowError, match="expired or was already used"):
            await service.handle_callback(state=start.state, code="auth-code-123")

    async def test_an_unknown_state_is_refused(self) -> None:
        repo = FakeIntegrationRepository()
        service = _service(repo=repo)

        with pytest.raises(OAuthFlowError, match="expired or was already used"):
            await service.handle_callback(state="not-a-real-state", code="whatever")

    async def test_an_expired_session_is_refused(self) -> None:
        repo = FakeIntegrationRepository()
        installed = await _install_notion(repo)
        service = _service(repo=repo)

        start = await service.start(
            workspace_id=WORKSPACE_ID, installed_server_id=installed, user_id="user-1"
        )
        # Backdate the session past its TTL rather than sleeping ten
        # minutes in a test.
        repo.oauth_sessions[start.state]["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)

        with pytest.raises(OAuthFlowError, match="expired or was already used"):
            await service.handle_callback(state=start.state, code="auth-code-123")

    async def test_a_non_2xx_token_response_is_refused_without_leaking_provider_detail(
        self,
    ) -> None:
        repo = FakeIntegrationRepository()
        installed = await _install_notion(repo)
        transport = _token_transport(
            {"error": "invalid_grant", "error_description": "the client secret is wrong"},
            status_code=400,
        )
        service = _service(repo=repo, transport=transport)

        start = await service.start(
            workspace_id=WORKSPACE_ID, installed_server_id=installed, user_id="user-1"
        )

        with pytest.raises(OAuthFlowError) as excinfo:
            await service.handle_callback(state=start.state, code="auth-code-123")
        # The provider's own error text (which can echo back client
        # secret detail) must never surface in the raised message.
        assert "client secret" not in str(excinfo.value)

        # And the install must not have been silently activated on a
        # failed exchange.
        assert repo.installed[installed].status is InstallStatus.PENDING_AUTH

    async def test_a_response_with_no_access_token_is_refused(self) -> None:
        repo = FakeIntegrationRepository()
        installed = await _install_notion(repo)
        transport = _token_transport({"token_type": "bearer"})
        service = _service(repo=repo, transport=transport)

        start = await service.start(
            workspace_id=WORKSPACE_ID, installed_server_id=installed, user_id="user-1"
        )

        with pytest.raises(OAuthFlowError, match="did not return an access token"):
            await service.handle_callback(state=start.state, code="auth-code-123")

    async def test_a_network_failure_reaching_the_token_endpoint_is_refused(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        repo = FakeIntegrationRepository()
        installed = await _install_notion(repo)
        service = _service(repo=repo, transport=httpx.MockTransport(handler))

        start = await service.start(
            workspace_id=WORKSPACE_ID, installed_server_id=installed, user_id="user-1"
        )

        with pytest.raises(OAuthFlowError, match="Could not reach"):
            await service.handle_callback(state=start.state, code="auth-code-123")
