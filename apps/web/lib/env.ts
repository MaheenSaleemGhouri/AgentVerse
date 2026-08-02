/**
 * Server-only required environment variables, validated once at import
 * time so a missing value fails startup loudly (CLAUDE.md §10) instead
 * of surfacing as an undefined-is-not-a-string error deep in a request.
 */

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

export const env = {
  databaseUrl: requireEnv("DATABASE_URL"),
  betterAuthSecret: requireEnv("BETTER_AUTH_SECRET"),
  betterAuthUrl: requireEnv("BETTER_AUTH_URL"),
  apiInternalUrl: requireEnv("API_INTERNAL_URL"),
  // The externally reachable origin of apps/api. Only needed to *show*
  // an identity provider where to send SCIM requests — optional, because
  // a deployment without SCIM configured has no reason to publish one,
  // and printing `apiInternalUrl` instead would hand an admin a URL that
  // silently fails from outside the cluster.
  apiPublicUrl: process.env.API_PUBLIC_URL,
  internalApiSecret: requireEnv("INTERNAL_API_SECRET"),
  githubClientId: process.env.GITHUB_CLIENT_ID,
  githubClientSecret: process.env.GITHUB_CLIENT_SECRET,
  // Optional, exactly like GitHub: a provider is registered only when
  // both halves are present, and the auth UI only renders a button for a
  // provider that is registered. An unconfigured Google button would be
  // a control that fails on click, which is the same defect as mock
  // authentication regardless of how real it looks.
  googleClientId: process.env.GOOGLE_CLIENT_ID,
  googleClientSecret: process.env.GOOGLE_CLIENT_SECRET,
} as const;
