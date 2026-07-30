"""Completes the OAuth2 flow the Phase 6 scaffolding left half-built.

`oauth_sessions`, its repository methods, and `OauthStartResponse` all
shipped in the original migration; nothing generated an authorization
URL or exchanged a code for a token, so the five oauth2 catalog entries
(Notion, Linear, Jira, HubSpot, Cloudflare) could install but never
finish connecting (`docs/PHASE-6-MCP-CHECKLIST.md` gap #1). This module
is that missing piece — `OauthFlowService.start` and `.handle_callback`.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from agentverse_shared.security.envelope import (
    CredentialVault,
    SealedSecret,
    credential_aad,
    hint_for,
)

from agentverse_api.orchestration_service.domain.integration_entities import (
    AuthScheme,
    InstallStatus,
    McpServer,
)
from agentverse_api.orchestration_service.domain.ports.integration_repository import (
    IntegrationRepository,
)
from agentverse_api.orchestration_service.infrastructure.oauth.providers import (
    OAuthProviderConfig,
)

#: How long an in-flight exchange stays valid (matches the router's own
#: `OAUTH_SESSION_TTL` docstring: the row holds a live PKCE verifier).
SESSION_TTL = timedelta(minutes=10)

#: Credential keys the resolved token is stored under. `credential_placement`
#: (apps/worker/src/agentverse_worker/mcp/factory.py) sends any `oauth2`
#: credential as `Authorization: Bearer <value>` regardless of key name;
#: the refresh token has no consumer yet (see `handle_callback`) and is
#: stored under `none` purely so a provider that later needs it does not
#: have to ask the user to reconnect.
ACCESS_TOKEN_KEY = "OAUTH_ACCESS_TOKEN"
REFRESH_TOKEN_KEY = "OAUTH_REFRESH_TOKEN"

#: A generous but bounded wait for a provider's token endpoint — long
#: enough for a slow provider, short enough that a hung provider does
#: not hold this request open indefinitely (CLAUDE.md §7: no unbounded
#: synchronous wait).
TOKEN_EXCHANGE_TIMEOUT_SECONDS = 15.0


class OAuthFlowError(Exception):
    """Raised for every failure mode `handle_callback` can hit.

    One exception type, not several, because the router's job is the
    same regardless of which step failed: redirect the browser back to
    the integrations page with an error, never leak provider response
    detail (which can include the client secret's own error text) into
    a response body.
    """


@dataclass(frozen=True, slots=True)
class OAuthStart:
    authorization_url: str
    state: str
    expires_at: datetime


def _generate_pkce_pair() -> tuple[str, str]:
    """`(code_verifier, code_challenge)` for S256 PKCE (RFC 7636).

    A verifier is generated per attempt rather than reused, so two
    concurrent connect attempts from the same workspace never share one
    — reuse would mean the second exchange invalidates the first even if
    the first's callback lands second.
    """
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class OAuthFlowService:
    def __init__(
        self,
        *,
        repo: IntegrationRepository,
        vault: CredentialVault,
        providers: dict[str, OAuthProviderConfig],
        callback_url: str,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._repo = repo
        self._vault = vault
        self._providers = providers
        self._callback_url = callback_url
        self._http = http_client

    def _provider_for(self, entry: McpServer) -> OAuthProviderConfig:
        provider = self._providers.get(entry.slug)
        if provider is None:
            raise OAuthFlowError(
                f"{entry.name} is not configured for OAuth on this deployment. "
                "Its client id/secret pair is unset."
            )
        return provider

    async def start(
        self,
        *,
        workspace_id: str,
        installed_server_id: str,
        user_id: str,
    ) -> OAuthStart:
        """Builds the authorization URL and records the in-flight attempt.

        Requires a catalog install (`mcp_server_id` not null) — the
        provider registry is keyed by catalog slug, so a custom-registered
        server has nothing to look one up by. Custom servers authenticate
        via the manual credential form instead.
        """
        server = await self._repo.get_installed(
            workspace_id=workspace_id, installed_server_id=installed_server_id
        )
        if server is None:
            raise OAuthFlowError("Integration not found.")
        if server.mcp_server_id is None:
            raise OAuthFlowError("Custom servers authenticate with a manual credential, not OAuth.")

        entry = await self._repo.get_catalog_entry(server_id=server.mcp_server_id)
        if entry is None or entry.auth_scheme is not AuthScheme.OAUTH2:
            raise OAuthFlowError("This integration does not use OAuth.")

        provider = self._provider_for(entry)

        verifier, challenge = _generate_pkce_pair()
        state = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + SESSION_TTL

        sealed_verifier = self._vault.seal(
            verifier,
            associated_data=credential_aad(
                workspace_id=workspace_id,
                installed_server_id=installed_server_id,
                key="__oauth_pkce_verifier__",
            ),
        )
        await self._repo.create_oauth_session(
            workspace_id=workspace_id,
            installed_server_id=installed_server_id,
            state=state,
            verifier_ciphertext=sealed_verifier.ciphertext,
            wrapped_dek=sealed_verifier.wrapped_dek,
            key_version=sealed_verifier.key_version,
            redirect_uri=self._callback_url,
            requested_scopes=list(entry.oauth_scopes),
            started_by_user_id=user_id,
            expires_at=expires_at,
        )

        query = {
            "client_id": provider.client_id,
            "redirect_uri": self._callback_url,
            "response_type": "code",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if entry.oauth_scopes:
            query["scope"] = provider.scope_separator.join(entry.oauth_scopes)

        authorization_url = f"{provider.authorize_url}?{urlencode(query)}"
        return OAuthStart(authorization_url=authorization_url, state=state, expires_at=expires_at)

    async def handle_callback(self, *, state: str, code: str) -> tuple[str, str]:
        """Consumes the session, exchanges the code, stores the token.

        Returns `(workspace_id, installed_server_id)` so the router can
        build the redirect back to the right integration page. Raises
        `OAuthFlowError` for every failure — an unknown/replayed state,
        an unconfigured provider, or a non-2xx token response — so the
        router has one place to turn any of them into a safe redirect.
        """
        session = await self._repo.consume_oauth_session(state=state)
        if session is None:
            raise OAuthFlowError("This authorization link has expired or was already used.")

        workspace_id = str(session["workspace_id"])
        installed_server_id = str(session["installed_server_id"])

        verifier = self._vault.open(
            _sealed_from_session(session),
            associated_data=credential_aad(
                workspace_id=workspace_id,
                installed_server_id=installed_server_id,
                key="__oauth_pkce_verifier__",
            ),
        )

        server = await self._repo.get_installed(
            workspace_id=workspace_id, installed_server_id=installed_server_id
        )
        if server is None or server.mcp_server_id is None:
            raise OAuthFlowError("Integration no longer exists.")
        entry = await self._repo.get_catalog_entry(server_id=server.mcp_server_id)
        if entry is None:
            raise OAuthFlowError("Integration no longer exists.")
        provider = self._provider_for(entry)

        token_response = await self._exchange_code(
            provider=provider,
            code=code,
            verifier=verifier,
            redirect_uri=str(session["redirect_uri"]),
        )

        access_token = token_response.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            # Deliberately no provider response detail in the message —
            # it can carry the client secret's own error text, which
            # must never reach a log line or an HTTP response body.
            raise OAuthFlowError("The provider did not return an access token.")

        await self._store_token(
            workspace_id=workspace_id,
            installed_server_id=installed_server_id,
            key=ACCESS_TOKEN_KEY,
            value=access_token,
            auth_scheme=AuthScheme.OAUTH2,
        )
        refresh_token = token_response.get("refresh_token")
        if isinstance(refresh_token, str) and refresh_token:
            await self._store_token(
                workspace_id=workspace_id,
                installed_server_id=installed_server_id,
                key=REFRESH_TOKEN_KEY,
                value=refresh_token,
                # `none`: nothing resolves this into a request yet — no
                # automatic-refresh consumer exists (a documented Phase 6
                # gap, not silently pretended-away here). Stored anyway so
                # a future refresh implementation does not have to make
                # every already-connected workspace reconnect.
                auth_scheme=AuthScheme.NONE,
            )

        if server.status is InstallStatus.PENDING_AUTH:
            await self._repo.update_installed(
                workspace_id=workspace_id,
                installed_server_id=installed_server_id,
                changes={"status": InstallStatus.ACTIVE},
            )

        return workspace_id, installed_server_id

    async def _exchange_code(
        self,
        *,
        provider: OAuthProviderConfig,
        code: str,
        verifier: str,
        redirect_uri: str,
    ) -> dict[str, object]:
        try:
            response = await self._http.post(
                provider.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": provider.client_id,
                    "client_secret": provider.client_secret,
                    "code_verifier": verifier,
                },
                headers={"Accept": "application/json"},
                timeout=TOKEN_EXCHANGE_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise OAuthFlowError("Could not reach the provider's token endpoint.") from exc

        if response.status_code >= 400:
            raise OAuthFlowError(
                f"The provider rejected the token exchange (HTTP {response.status_code})."
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise OAuthFlowError("The provider returned a non-JSON token response.") from exc
        if not isinstance(body, dict):
            raise OAuthFlowError("The provider returned an unexpected token response shape.")
        return body

    async def _store_token(
        self,
        *,
        workspace_id: str,
        installed_server_id: str,
        key: str,
        value: str,
        auth_scheme: AuthScheme,
    ) -> None:
        sealed = self._vault.seal(
            value,
            associated_data=credential_aad(
                workspace_id=workspace_id,
                installed_server_id=installed_server_id,
                key=key,
            ),
        )
        await self._repo.put_credential(
            workspace_id=workspace_id,
            installed_server_id=installed_server_id,
            key=key,
            auth_scheme=auth_scheme,
            ciphertext=sealed.ciphertext,
            wrapped_dek=sealed.wrapped_dek,
            key_version=sealed.key_version,
            hint=hint_for(value),
            expires_at=None,
        )


def _sealed_from_session(session: dict[str, object]) -> SealedSecret:
    # Keyed `code_verifier_ciphertext`, matching what
    # `SqlIntegrationRepository.consume_oauth_session` actually returns
    # (its DB column name), not the port method's `verifier_ciphertext`
    # parameter name — the fake test double mirrors this same shape.
    return SealedSecret(
        ciphertext=session["code_verifier_ciphertext"],  # type: ignore[arg-type]
        wrapped_dek=session["wrapped_dek"],  # type: ignore[arg-type]
        key_version=str(session["key_version"]),
    )
