import { betterAuth } from "better-auth";
import { genericOAuth, jwt, twoFactor } from "better-auth/plugins";
import { Pool } from "pg";

import { env } from "@/lib/env";
import { sendEmail } from "@/lib/email/sender";
import { hashPassword, verifyPassword } from "@/lib/password-hashing";
import { reportAuthEvent } from "@/lib/report-auth-event";
import { discoveryUrlFor, loadSsoProviders } from "@/lib/sso-providers";

// Top-level await: the provider list has to exist before `betterAuth()`
// is constructed, because `genericOAuth` reads it once at init (see
// `lib/sso-providers.ts` for why per-request resolution isn't possible).
// Resolves to `[]` if apps/api is unreachable, so a boot-time blip
// degrades SSO rather than breaking all sign-in.
const ssoProviders = await loadSsoProviders();

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
    // Reverted from Increment 7.1's `true`: this deployment has no
    // verified Resend sending domain, so a verification email can only
    // ever reach the Resend account owner's own address (sandbox
    // restriction) — gating login on it would lock out every other
    // tester/signup. `sendOnSignUp` below still fires a best-effort
    // verification email; login just never waits on it. Flip back to
    // `true` once a domain is verified in Resend.
    requireEmailVerification: false,
    minPasswordLength: 8,
    maxPasswordLength: 128,
    password: {
      hash: hashPassword,
      verify: verifyPassword,
    },
    sendResetPassword: async ({ user, url }) => {
      await sendEmail({
        to: user.email,
        subject: "Reset your AgentVerse password",
        body: `Reset your password: ${url}`,
      });
    },
  },

  emailVerification: {
    sendOnSignUp: true,
    autoSignInAfterVerification: true,
    sendVerificationEmail: async ({ user, url }) => {
      await sendEmail({
        to: user.email,
        subject: "Verify your AgentVerse email",
        body: `Verify your email address: ${url}`,
      });
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
    // Org SSO (Increment 8): one generic OIDC provider per enabled
    // organization config. Registered only when at least one exists, so
    // a deployment with no SSO configured carries no extra surface.
    ...(ssoProviders.length > 0
      ? [
          genericOAuth({
            config: ssoProviders.map((provider) => ({
              providerId: provider.providerId,
              clientId: provider.clientId,
              clientSecret: provider.clientSecret,
              discoveryUrl: discoveryUrlFor(provider.issuerUrl),
              scopes: ["openid", "email", "profile"],
            })),
          }),
        ]
      : []),
    // TOTP two-factor (Increment 7.2) — Better Auth's own vetted plugin,
    // never hand-rolled crypto (same reasoning as Argon2id, ADR-0005).
    // Its table is authored by Alembic (`two_factor`), so the field
    // mapping below must match migration `c1e5a8d3f704` exactly.
    // apps/api needs no change: 2FA gates sign-in, before a JWT exists.
    twoFactor({
      issuer: "AgentVerse",
      // Field renames for plugin-owned columns must live here, not in the
      // top-level `user.fields` — Better Auth's `mergeSchema` only applies
      // overrides to the schema of the plugin that declared the field, so
      // mapping `twoFactorEnabled` at the top level is silently ignored
      // and the query goes out with the camelCase name (caught by a real
      // signup returning `column "twoFactorEnabled" does not exist`).
      schema: {
        user: {
          fields: {
            twoFactorEnabled: "two_factor_enabled",
          },
        },
        twoFactor: {
          modelName: "two_factor",
          fields: {
            backupCodes: "backup_codes",
            userId: "user_id",
            failedVerificationCount: "failed_verification_count",
            lockedUntil: "locked_until",
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
