import "server-only";

import { loadSamlProviders } from "@/lib/saml";
import { loadSsoProviders } from "@/lib/sso-providers";

/**
 * The org SSO providers a signed-out visitor may choose on the login
 * page. Derived from the *same* `loadSsoProviders()` call `lib/auth.ts`
 * registers from, so a provider can never be offered-but-unregistered or
 * registered-but-hidden — the one-source-of-truth rule
 * `lib/social-providers.ts` already follows.
 *
 * Deliberately drops `clientSecret` and `clientId`: this value crosses
 * into a Client Component, and nothing there needs either.
 */
export interface SsoLoginOption {
  providerId: string;
  organizationId: string;
  /** OIDC goes through Better Auth's plugin; SAML has its own route
   * pair, so the button has to know which to start. */
  protocol: "oidc" | "saml";
}

export async function ssoLoginOptions(): Promise<SsoLoginOption[]> {
  const [oidc, saml] = await Promise.all([loadSsoProviders(), loadSamlProviders()]);
  return [
    ...oidc.map((provider) => ({
      providerId: provider.providerId,
      organizationId: provider.organizationId,
      protocol: "oidc" as const,
    })),
    ...saml.map((provider) => ({
      providerId: provider.providerId,
      organizationId: provider.organizationId,
      protocol: "saml" as const,
    })),
  ];
}
