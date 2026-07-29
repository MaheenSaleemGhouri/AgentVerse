import "server-only";

/**
 * Which OAuth providers are actually usable, resolved on the server.
 *
 * Server-only so the decision reads the real secrets rather than needing
 * a `NEXT_PUBLIC_*` mirror of them — §10 audits every `NEXT_PUBLIC_`
 * addition precisely because it ships to the browser, and "is Google
 * configured" does not need to.
 *
 * One source of truth with `lib/auth.ts`: both derive from the same env
 * pair, so a provider can never be registered-but-hidden or
 * shown-but-unregistered.
 */

export type SocialProvider = "google" | "github";

export function enabledSocialProviders(): SocialProvider[] {
  const providers: SocialProvider[] = [];
  if (process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET) providers.push("google");
  if (process.env.GITHUB_CLIENT_ID && process.env.GITHUB_CLIENT_SECRET) providers.push("github");
  return providers;
}
