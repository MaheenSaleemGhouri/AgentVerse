import type { SsoPreset, SsoProtocol } from "@/lib/api/sso";

/**
 * Named-IdP presets (Increment 8c).
 *
 * **UI convenience only.** A preset pre-fills the *generic* OIDC/SAML
 * form fields and points the admin at the right console — it never
 * changes how the protocol is executed. There is deliberately no
 * per-vendor server code: the Azure AD preset produces exactly the same
 * generic OIDC configuration a hand-filled form would, which is the
 * whole point of `protocol` being generic in the first place.
 */
export interface SsoPresetDefinition {
  readonly id: SsoPreset;
  readonly label: string;
  readonly protocol: SsoProtocol;
  /** `{tenant}`-style placeholders the admin replaces. */
  readonly issuerUrlTemplate?: string;
  readonly hint: string;
}

export const SSO_PRESETS: readonly SsoPresetDefinition[] = [
  {
    id: "google_workspace",
    label: "Google Workspace",
    protocol: "oidc",
    issuerUrlTemplate: "https://accounts.google.com",
    hint: "Create an OAuth 2.0 Client ID in Google Cloud Console → APIs & Services → Credentials.",
  },
  {
    id: "azure_ad",
    label: "Microsoft Entra ID (Azure AD)",
    protocol: "oidc",
    issuerUrlTemplate: "https://login.microsoftonline.com/{tenant-id}/v2.0",
    hint: "Register an app in Entra ID → App registrations, then add a client secret.",
  },
  {
    id: "okta",
    label: "Okta",
    protocol: "oidc",
    issuerUrlTemplate: "https://{your-domain}.okta.com/oauth2/default",
    hint: "Create an OIDC Web application in the Okta Admin Console.",
  },
  {
    id: "auth0",
    label: "Auth0",
    protocol: "oidc",
    issuerUrlTemplate: "https://{your-tenant}.auth0.com/",
    hint: "Create a Regular Web Application in the Auth0 Dashboard.",
  },
  {
    id: "generic",
    label: "Generic OIDC",
    protocol: "oidc",
    hint: "Any OpenID Connect provider that exposes a discovery document.",
  },
  {
    id: "generic",
    label: "Generic SAML 2.0",
    protocol: "saml",
    hint: "Any SAML 2.0 identity provider. Supply the IdP metadata URL below.",
  },
] as const;
