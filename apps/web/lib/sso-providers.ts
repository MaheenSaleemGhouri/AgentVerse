import "server-only";

import { env } from "@/lib/env";

/**
 * Loads enabled org SSO providers from apps/api at application start and
 * shapes them for Better Auth's `genericOAuth` plugin.
 *
 * ## Why this happens at startup and not per request
 *
 * `genericOAuth` reads its provider list **once, at plugin
 * initialisation** — verified in the plugin's own source, which iterates
 * `options.config` inside `init()`. It has no hook for resolving a
 * provider per request, so a config saved in the UI becomes usable on
 * the next application start, not immediately. That is a real
 * operational constraint, surfaced in the SSO settings UI rather than
 * hidden. The alternative — hand-writing the OIDC authorization/token
 * exchange to get per-request lookup — would mean owning
 * security-critical protocol code that a vetted library already
 * implements.
 *
 * ## Failure behaviour
 *
 * Fails **open to an empty list**: if apps/api is unreachable at boot,
 * SSO providers are simply absent and password/social sign-in still
 * work. Throwing here would take the entire auth system down for every
 * user because one optional feature could not be configured.
 */
export interface SsoProviderConfig {
  organizationId: string;
  providerId: string;
  issuerUrl: string;
  clientId: string;
  clientSecret: string;
}

interface ResolvedProviderResponse {
  organization_id: string;
  provider_id: string;
  issuer_url: string;
  client_id: string;
  client_secret: string;
}

export async function loadSsoProviders(): Promise<SsoProviderConfig[]> {
  try {
    const response = await fetch(`${env.apiInternalUrl}/internal/sso-providers`, {
      headers: { "X-Internal-Secret": env.internalApiSecret },
      cache: "no-store",
    });
    if (!response.ok) {
      console.error(`loadSsoProviders: apps/api returned ${response.status}`);
      return [];
    }
    const rows = (await response.json()) as ResolvedProviderResponse[];
    return rows.map((row) => ({
      organizationId: row.organization_id,
      providerId: row.provider_id,
      issuerUrl: row.issuer_url,
      clientId: row.client_id,
      clientSecret: row.client_secret,
    }));
  } catch (error) {
    console.error("loadSsoProviders: could not reach apps/api, starting without SSO", error);
    return [];
  }
}

/** OIDC discovery document location for an issuer, per the spec. */
export function discoveryUrlFor(issuerUrl: string): string {
  return `${issuerUrl.replace(/\/$/, "")}/.well-known/openid-configuration`;
}
