import { betterAuth } from "better-auth";
import { jwt } from "better-auth/plugins";
import { Pool } from "pg";

import { env } from "@/lib/env";
import { hashPassword, verifyPassword } from "@/lib/password-hashing";
import { reportAuthEvent } from "@/lib/report-auth-event";

/**
 * Better Auth server instance (ADR-0005). Schema is authored by Alembic
 * (apps/api) — the `fields` mappings below point at those exact
 * snake_case tables/columns; this instance never runs its own migration
 * tooling against the database (CLAUDE.md §8: Alembic only).
 */
export const auth = betterAuth({
  secret: env.betterAuthSecret,
  baseURL: env.betterAuthUrl,
  database: new Pool({ connectionString: env.databaseUrl }),

  user: {
    modelName: "users",
    fields: {
      emailVerified: "email_verified",
      createdAt: "created_at",
      updatedAt: "updated_at",
    },
  },
  session: {
    modelName: "sessions",
    fields: {
      userId: "user_id",
      expiresAt: "expires_at",
      ipAddress: "ip_address",
      userAgent: "user_agent",
      createdAt: "created_at",
      updatedAt: "updated_at",
    },
  },
  account: {
    modelName: "accounts",
    fields: {
      userId: "user_id",
      accountId: "account_id",
      providerId: "provider_id",
      accessToken: "access_token",
      refreshToken: "refresh_token",
      accessTokenExpiresAt: "access_token_expires_at",
      refreshTokenExpiresAt: "refresh_token_expires_at",
      idToken: "id_token",
      createdAt: "created_at",
      updatedAt: "updated_at",
    },
  },
  verification: {
    modelName: "verifications",
    fields: {
      expiresAt: "expires_at",
      createdAt: "created_at",
      updatedAt: "updated_at",
    },
  },

  emailAndPassword: {
    enabled: true,
    requireEmailVerification: false,
    minPasswordLength: 8,
    maxPasswordLength: 128,
    password: {
      hash: hashPassword,
      verify: verifyPassword,
    },
  },

  // GitHub since Phase 1 (ADR-0005); Google added with the auth UI
  // rebuild, which shows both buttons. Each is registered only when its
  // credentials are present, and the pages ask `enabledSocialProviders()`
  // what to render — so a provider without keys is absent from the UI
  // rather than being a button that fails on click.
  socialProviders: {
    ...(env.githubClientId && env.githubClientSecret
      ? { github: { clientId: env.githubClientId, clientSecret: env.githubClientSecret } }
      : {}),
    ...(env.googleClientId && env.googleClientSecret
      ? { google: { clientId: env.googleClientId, clientSecret: env.googleClientSecret } }
      : {}),
  },

  // apps/api verifies these against Better Auth's JWKS endpoint
  // (ADR-0005) — no shared secret between the two services.
  plugins: [
    jwt({
      schema: {
        jwks: {
          fields: {
            publicKey: "public_key",
            privateKey: "private_key",
            createdAt: "created_at",
          },
        },
      },
    }),
  ],

  databaseHooks: {
    user: {
      create: {
        after: async (user) => {
          await reportAuthEvent("auth.signup", user.id);
        },
      },
    },
    session: {
      create: {
        after: async (session) => {
          await reportAuthEvent("auth.login", session.userId);
        },
      },
    },
  },
});
