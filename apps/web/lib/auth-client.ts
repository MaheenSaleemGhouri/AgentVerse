"use client";

import { createAuthClient } from "better-auth/react";
import { genericOAuthClient, twoFactorClient } from "better-auth/client/plugins";

export const authClient = createAuthClient({
  baseURL: process.env.NEXT_PUBLIC_BETTER_AUTH_URL,
  // Mirrors the server's `twoFactor()` plugin (Increment 7.2) — the
  // client plugin is what exposes `authClient.twoFactor.*` and makes a
  // sign-in that needs a second factor return `twoFactorRedirect`
  // instead of a session.
  // `genericOAuthClient` exposes `authClient.signIn.oauth2({providerId})`,
  // which is how the login page starts an org SSO sign-in (Increment 8).
  plugins: [twoFactorClient(), genericOAuthClient()],
});

export const { signIn, signUp, signOut, useSession } = authClient;
