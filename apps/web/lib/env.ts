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
  internalApiSecret: requireEnv("INTERNAL_API_SECRET"),
  githubClientId: process.env.GITHUB_CLIENT_ID,
  githubClientSecret: process.env.GITHUB_CLIENT_SECRET,
} as const;
