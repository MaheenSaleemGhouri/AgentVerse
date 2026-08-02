import { NextResponse } from "next/server";

import { buildSamlClient, findSamlProvider } from "@/lib/saml";

/**
 * Starts a SAML sign-in: builds a signed AuthnRequest and redirects the
 * browser to the organization's IdP.
 *
 * Unlike the OIDC providers, SAML providers are resolved **per request**
 * rather than at boot — this route owns its own flow instead of being
 * registered into a plugin whose config is fixed at init, so a newly
 * enabled SAML config works immediately with no restart.
 */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ providerId: string }> }
): Promise<NextResponse> {
  const { providerId } = await params;
  const provider = await findSamlProvider(providerId);
  if (!provider) {
    return NextResponse.redirect(
      new URL("/login?error=sso_unavailable", process.env.BETTER_AUTH_URL ?? "http://localhost:3000")
    );
  }

  try {
    const saml = buildSamlClient(provider);
    const redirectUrl = await saml.getAuthorizeUrlAsync("", undefined, {});
    return NextResponse.redirect(redirectUrl);
  } catch (error) {
    console.error("saml/login: could not build the AuthnRequest", error);
    return NextResponse.redirect(
      new URL("/login?error=sso_failed", process.env.BETTER_AUTH_URL ?? "http://localhost:3000")
    );
  }
}
