"""Request/response schemas for org SSO configuration (CLAUDE.md §7).

`SsoConfigurationResponse` deliberately has no `client_secret` field —
the secret is write-only by construction, not by remembering to strip it.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from agentverse_api.auth_service.domain.sso import SsoPreset, SsoProtocol


class SaveSsoConfigurationRequest(BaseModel):
    protocol: SsoProtocol
    preset: SsoPreset = SsoPreset.GENERIC
    issuer_url: str | None = Field(default=None, max_length=500)
    client_id: str | None = Field(default=None, max_length=255)
    #: Write-only. Omit to keep the currently stored secret — so editing
    #: the issuer URL never requires re-entering it.
    client_secret: str | None = Field(default=None, max_length=500)
    #: Protocol-specific extras (SAML IdP metadata URL / signing
    #: certificate, extra OIDC scopes). JSONB-backed, so a new protocol
    #: field needs no migration.
    protocol_config: dict[str, str] = Field(default_factory=dict)
    enabled: bool = False


class SsoConfigurationResponse(BaseModel):
    id: str
    organization_id: str
    protocol: SsoProtocol
    preset: SsoPreset
    issuer_url: str | None
    client_id: str | None
    has_client_secret: bool
    protocol_config: dict[str, str]
    enabled: bool
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime


class ResolvedSsoProviderResponse(BaseModel):
    """Internal-only (see `routes/internal_sso_providers.py`). This is the
    one schema in the codebase that intentionally carries a plaintext
    client secret, and it is reachable only behind the shared-secret
    internal check — never from `/api/v1`.
    """

    organization_id: str
    provider_id: str
    issuer_url: str
    client_id: str
    client_secret: str


class ResolvedSamlProviderResponse(BaseModel):
    """Internal-only. Unlike the OIDC counterpart this carries no secret —
    a SAML IdP's signing certificate is public by design.
    """

    organization_id: str
    provider_id: str
    entry_point: str
    idp_certificate: str
    idp_entity_id: str
