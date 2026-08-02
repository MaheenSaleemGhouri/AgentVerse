import "server-only";

import { SAML } from "@node-saml/node-saml";

import { env } from "@/lib/env";

/**
 * SAML 2.0 service provider (Increment 8b).
 *
 * Every signature and assertion check is delegated to
 * `@node-saml/node-saml` — a maintained, vetted implementation. Nothing
 * in this file parses or verifies XML itself: hand-rolled XML signature
 * verification is the single most commonly broken part of SAML (signature
 * wrapping, comment truncation, canonicalisation bugs), and CLAUDE.md §10
 * rules it out explicitly.
 *
 * Unlike the OIDC path there is no secret to decrypt: SAML trust rests on
 * the IdP's **public** signing certificate, so these configs need no
 * vault interaction.
 */

export interface SamlProviderConfig {
  organizationId: string;
  providerId: string;
  entryPoint: string;
  idpCertificate: string;
  idpEntityId: string;
}

interface ResolvedSamlResponse {
  organization_id: string;
  provider_id: string;
  entry_point: string;
  idp_certificate: string;
  idp_entity_id: string;
}

/** Same fail-open contract as `loadSsoProviders` — see that file. */
export async function loadSamlProviders(): Promise<SamlProviderConfig[]> {
  try {
    const response = await fetch(`${env.apiInternalUrl}/internal/sso-providers/saml`, {
      headers: { "X-Internal-Secret": env.internalApiSecret },
      cache: "no-store",
    });
    if (!response.ok) {
      console.error(`loadSamlProviders: apps/api returned ${response.status}`);
      return [];
    }
    const rows = (await response.json()) as ResolvedSamlResponse[];
    return rows.map((row) => ({
      organizationId: row.organization_id,
      providerId: row.provider_id,
      entryPoint: row.entry_point,
      idpCertificate: row.idp_certificate,
      idpEntityId: row.idp_entity_id,
    }));
  } catch (error) {
    console.error("loadSamlProviders: could not reach apps/api", error);
    return [];
  }
}

export async function findSamlProvider(
  providerId: string
): Promise<SamlProviderConfig | undefined> {
  const providers = await loadSamlProviders();
  return providers.find((provider) => provider.providerId === providerId);
}

/** This service provider's entity id — stable, and what the IdP must be
 * configured to expect as the Audience. */
export function serviceProviderEntityId(): string {
  return `${env.betterAuthUrl.replace(/\/$/, "")}/saml`;
}

export function assertionConsumerServiceUrl(providerId: string): string {
  return `${env.betterAuthUrl.replace(/\/$/, "")}/api/sso/saml/${providerId}/acs`;
}

export function buildSamlClient(provider: SamlProviderConfig): SAML {
  return new SAML({
    entryPoint: provider.entryPoint,
    // node-saml calls this `idpCert`; it is the IdP's public signing
    // certificate, and supplying it is what makes assertion validation
    // meaningful rather than decorative.
    idpCert: provider.idpCertificate,
    issuer: serviceProviderEntityId(),
    callbackUrl: assertionConsumerServiceUrl(provider.providerId),
    // Non-negotiable checks. `wantAssertionsSigned` is the one that
    // actually stops signature-wrapping attacks: without it an attacker
    // can present a signed *response* wrapping an unsigned assertion.
    wantAuthnResponseSigned: true,
    wantAssertionsSigned: true,
    signatureAlgorithm: "sha256",
    digestAlgorithm: "sha256",
    identifierFormat: "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
    audience: serviceProviderEntityId(),
    ...(provider.idpEntityId ? { idpIssuer: provider.idpEntityId } : {}),
  });
}

/** The email an assertion asserts, tried in the order IdPs actually use. */
export function emailFromProfile(profile: Record<string, unknown>): string | null {
  const candidates = [
    profile.email,
    profile.nameID,
    profile["http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"],
    profile["urn:oid:1.2.840.113549.1.9.1"],
  ];
  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate.includes("@")) {
      return candidate.toLowerCase();
    }
  }
  return null;
}

export function displayNameFromProfile(
  profile: Record<string, unknown>,
  fallback: string
): string {
  const candidates = [
    profile.displayName,
    profile["http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"],
    profile["urn:oid:2.16.840.1.113730.3.1.241"],
  ];
  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
  }
  return fallback;
}
