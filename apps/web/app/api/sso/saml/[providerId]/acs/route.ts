import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";
import { env } from "@/lib/env";
import { reportAuthEvent } from "@/lib/report-auth-event";
import {
  buildSamlClient,
  displayNameFromProfile,
  emailFromProfile,
  findSamlProvider,
} from "@/lib/saml";
import { prepareSessionCookie } from "@/lib/session-cookie";

/**
 * Assertion Consumer Service — where the IdP POSTs its signed response.
 *
 * `validatePostResponseAsync` performs every security-critical check
 * (XML signature, certificate match, audience, conditions/NotOnOrAfter,
 * InResponseTo). If it throws or reports an unsigned assertion, this
 * route redirects to an error rather than trusting anything in the
 * document — there is deliberately no "best effort" path that accepts a
 * partially-valid assertion.
 */

function loginError(reason: string): NextResponse {
  return NextResponse.redirect(new URL(`/login?error=${reason}`, env.betterAuthUrl));
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ providerId: string }> }
): Promise<NextResponse> {
  const { providerId } = await params;
  const provider = await findSamlProvider(providerId);
  if (!provider) return loginError("sso_unavailable");

  let email: string;
  let displayName: string;
  try {
    const form = await request.formData();
    const samlResponse = form.get("SAMLResponse");
    if (typeof samlResponse !== "string") return loginError("sso_failed");

    const saml = buildSamlClient(provider);
    const { profile, loggedOut } = await saml.validatePostResponseAsync({
      SAMLResponse: samlResponse,
    });
    if (loggedOut || !profile) return loginError("sso_failed");

    const resolved = emailFromProfile(profile as unknown as Record<string, unknown>);
    if (!resolved) {
      // An assertion with no email is unusable: it is the only identifier
      // this platform links accounts by. Failing here is better than
      // inventing a placeholder that silently creates orphan accounts.
      console.error("saml/acs: assertion carried no email claim");
      return loginError("sso_no_email");
    }
    email = resolved;
    displayName = displayNameFromProfile(
      profile as unknown as Record<string, unknown>,
      email
    );
  } catch (error) {
    // Covers signature failure, audience mismatch, expiry — every
    // rejection path node-saml raises. Logged for the admin, opaque to
    // the browser.
    console.error("saml/acs: assertion rejected", error);
    return loginError("sso_failed");
  }

  try {
    const ctx = await auth.$context;

    let user = await ctx.internalAdapter.findUserByEmail(email);
    if (!user) {
      // Just-in-time provisioning. `emailVerified: true` is correct and
      // deliberate: the IdP already authenticated this address, and
      // requiring a second AgentVerse-side verification would make SSO
      // users unable to sign in at all (Increment 7.1 enforces it).
      const created = await ctx.internalAdapter.createUser({
        email,
        name: displayName,
        emailVerified: true,
      });
      await reportAuthEvent("auth.signup", created.id);
      user = { user: created, accounts: [] };
    }

    const session = await ctx.internalAdapter.createSession(user.user.id, false);
    await reportAuthEvent("auth.login", user.user.id);

    const response = NextResponse.redirect(new URL("/dashboard", env.betterAuthUrl));
    // Same cookie posture as every other sign-in path (CLAUDE.md §7):
    // httpOnly + SameSite, Secure whenever the origin is HTTPS — taken
    // from Better Auth's own resolved attributes rather than restated, and
    // signed the way Better Auth signs it (see lib/session-cookie.ts).
    const cookie = await prepareSessionCookie({
      token: session.token,
      secret: env.betterAuthSecret,
      attributes: ctx.authCookies.sessionToken.attributes,
      expiresAt: session.expiresAt,
    });
    response.cookies.set(ctx.authCookies.sessionToken.name, cookie.value, cookie.options);
    return response;
  } catch (error) {
    console.error("saml/acs: could not establish a session", error);
    return loginError("sso_failed");
  }
}
