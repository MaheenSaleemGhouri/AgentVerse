"""Org-scoped SSO configuration use cases (Increment 8).

The client secret is sealed with the **existing** `CredentialVault`
AES-256-GCM envelope already used for MCP integration credentials —
never new crypto (CLAUDE.md §10), never stored or logged in plaintext,
and never returned by any read path.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentverse_shared.security.envelope import CredentialVault, SealedSecret

from agentverse_api.auth_service.application.audit_service import AuditService
from agentverse_api.auth_service.domain.entities import SsoConfiguration
from agentverse_api.auth_service.domain.ports import SsoConfigurationRepository
from agentverse_api.auth_service.domain.sso import SsoPreset, SsoProtocol


def _associated_data(*, organization_id: str, protocol: SsoProtocol) -> bytes:
    """Binds ciphertext to the row it belongs to — a secret copied to a
    different organization's row fails to decrypt rather than silently
    becoming that organization's credential (the same reasoning the MCP
    credential vault uses).
    """
    return f"sso:{organization_id}:{protocol.value}".encode()


@dataclass(frozen=True, slots=True)
class ResolvedSsoProvider:
    """One enabled OIDC config with its secret opened, ready to be
    registered as an OAuth provider.

    Returned **only** to the internal, shared-secret-authenticated
    provider-resolution endpoint — never to a browser-reachable route.
    apps/web needs the plaintext secret to perform the OAuth token
    exchange, and re-implementing the AES-256-GCM envelope in TypeScript
    to get it there would mean two independent crypto implementations of
    the same format (CLAUDE.md §16, and a second place to get it wrong).
    """

    organization_id: str
    provider_id: str
    issuer_url: str
    client_id: str
    client_secret: str


@dataclass(frozen=True, slots=True)
class ResolvedSamlProvider:
    """One enabled SAML config, resolved for apps/web's service provider.

    No secret to open: SAML trust is established by the IdP's **signing
    certificate**, which is public by definition — the assertion is
    verified against it, nothing is encrypted with it. That is why this
    carries no vault interaction while the OIDC resolver does.
    """

    organization_id: str
    provider_id: str
    entry_point: str
    idp_certificate: str
    idp_entity_id: str


@dataclass(slots=True)
class SsoService:
    configurations: SsoConfigurationRepository
    vault: CredentialVault
    audit: AuditService

    async def list_configurations(self, organization_id: str) -> list[SsoConfiguration]:
        return await self.configurations.list_for_organization(organization_id)

    async def save_configuration(
        self,
        *,
        organization_id: str,
        protocol: SsoProtocol,
        preset: SsoPreset,
        issuer_url: str | None,
        client_id: str | None,
        client_secret: str | None,
        protocol_config: dict[str, str],
        enabled: bool,
        actor_user_id: str,
    ) -> SsoConfiguration:
        sealed: tuple[bytes, bytes, str] | None = None
        if client_secret:
            secret = self.vault.seal(
                client_secret,
                associated_data=_associated_data(
                    organization_id=organization_id, protocol=protocol
                ),
            )
            sealed = (secret.ciphertext, secret.wrapped_dek, secret.key_version)

        config = await self.configurations.upsert(
            organization_id=organization_id,
            protocol=protocol,
            preset=preset,
            issuer_url=issuer_url,
            client_id=client_id,
            sealed_secret=sealed,
            protocol_config=protocol_config,
            enabled=enabled,
            actor_user_id=actor_user_id,
        )
        await self.audit.record(
            action="sso.configured",
            outcome="success",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            target=config.id,
            # Deliberately records *which* protocol/preset and whether it
            # is live — never the client id or secret.
            metadata={
                "protocol": protocol.value,
                "preset": preset.value,
                "enabled": str(enabled).lower(),
            },
        )
        return config

    async def delete_configuration(
        self, *, organization_id: str, config_id: str, actor_user_id: str
    ) -> None:
        await self.audit.record(
            action="sso.deleted",
            outcome="success",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            target=config_id,
        )
        await self.configurations.delete(organization_id=organization_id, config_id=config_id)

    async def resolve_enabled_oidc_providers(self) -> list[ResolvedSsoProvider]:
        """Opens the sealed secret for every enabled OIDC config.

        A config missing any of issuer/client id/secret is skipped rather
        than returned half-built — a provider registered without a secret
        fails at the token exchange with an opaque error from the IdP,
        which is far harder to diagnose than simply not appearing.
        """
        resolved: list[ResolvedSsoProvider] = []
        for config, sealed in await self.configurations.list_enabled_sealed(SsoProtocol.OIDC):
            if not config.issuer_url or not config.client_id or sealed is None:
                continue
            ciphertext, wrapped_dek, key_version = sealed
            secret = self.vault.open(
                SealedSecret(
                    ciphertext=ciphertext, wrapped_dek=wrapped_dek, key_version=key_version
                ),
                associated_data=_associated_data(
                    organization_id=config.organization_id, protocol=SsoProtocol.OIDC
                ),
            )
            resolved.append(
                ResolvedSsoProvider(
                    organization_id=config.organization_id,
                    # Encodes the organization, so the OAuth callback knows
                    # which org's provider completed without a second lookup.
                    provider_id=f"sso-{config.organization_id}",
                    issuer_url=config.issuer_url,
                    client_id=config.client_id,
                    client_secret=secret,
                )
            )
        return resolved

    async def resolve_enabled_saml_providers(self) -> list[ResolvedSamlProvider]:
        """Every enabled SAML config that has the two things a service
        provider cannot work without: the IdP's SSO endpoint and its
        signing certificate.

        A config missing either is skipped rather than surfaced —
        registering a SAML provider without a certificate would mean
        accepting *unverified* assertions, which is strictly worse than
        the provider not existing.
        """
        resolved: list[ResolvedSamlProvider] = []
        for config, _sealed in await self.configurations.list_enabled_sealed(SsoProtocol.SAML):
            extras = config.protocol_config
            entry_point = extras.get("idp_sso_url") or ""
            certificate = extras.get("idp_certificate") or ""
            if not entry_point or not certificate:
                continue
            resolved.append(
                ResolvedSamlProvider(
                    organization_id=config.organization_id,
                    provider_id=f"saml-{config.organization_id}",
                    entry_point=entry_point,
                    idp_certificate=certificate,
                    idp_entity_id=extras.get("idp_entity_id") or "",
                )
            )
        return resolved
