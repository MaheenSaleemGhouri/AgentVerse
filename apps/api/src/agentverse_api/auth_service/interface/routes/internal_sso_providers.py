"""`/internal/sso-providers` — resolves enabled OIDC configs, with their
client secrets decrypted, for apps/web to register as OAuth providers at
startup.

Not part of the public `/api/v1` surface and never browser-reachable:
protected by the same shared-secret check as `/internal/auth-events`
(CLAUDE.md §10 zero trust). This exists because the secret is sealed with
the Python `CredentialVault` — apps/web performs the OAuth token exchange
and needs the plaintext, and duplicating the envelope format in
TypeScript would mean two crypto implementations of one format.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agentverse_api.auth_service.application.sso_service import SsoService
from agentverse_api.auth_service.interface.dependencies.internal_service_auth import (
    require_internal_service,
)
from agentverse_api.auth_service.interface.dependencies.services import get_sso_service
from agentverse_api.auth_service.interface.schemas.sso import (
    ResolvedSamlProviderResponse,
    ResolvedSsoProviderResponse,
)

router = APIRouter(
    prefix="/internal/sso-providers",
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
)


@router.get("", response_model=list[ResolvedSsoProviderResponse])
async def list_resolved_sso_providers(
    service: SsoService = Depends(get_sso_service),
) -> list[ResolvedSsoProviderResponse]:
    providers = await service.resolve_enabled_oidc_providers()
    return [
        ResolvedSsoProviderResponse.model_validate(provider, from_attributes=True)
        for provider in providers
    ]


@router.get("/saml", response_model=list[ResolvedSamlProviderResponse])
async def list_resolved_saml_providers(
    service: SsoService = Depends(get_sso_service),
) -> list[ResolvedSamlProviderResponse]:
    providers = await service.resolve_enabled_saml_providers()
    return [
        ResolvedSamlProviderResponse.model_validate(provider, from_attributes=True)
        for provider in providers
    ]
