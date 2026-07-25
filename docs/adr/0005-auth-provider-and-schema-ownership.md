# ADR-0005: Authentication Provider Choice & Schema Ownership

## Context

`docs/roadmap.md` Phase 1 requires "email/password + OAuth via a managed provider (Clerk or Better Auth)." `CLAUDE.md` §7 requires identity to be "verified once at the gateway/dependency layer via a managed provider... services trust a signed token, never re-implement token parsing." §8 requires "Alembic only; no manual DDL against any environment" and a single Postgres system of record. §10 requires password hashing via "bcrypt/argon2, never custom crypto."

## Decision

**Provider: Better Auth**, not Clerk. Better Auth is self-hostable against our own Postgres rather than a third-party hosted user store — keeping one system of record instead of syncing a local mirror via webhooks. It ships a JWT plugin (JWKS endpoint, `EdDSA`/Ed25519 signing) purpose-built for a second service (here, `apps/api`) to verify sessions without sharing a secret.

**Schema ownership: Alembic authors every table, including Better Auth's.** Better Auth's own migration CLI is never run against this database — `CLAUDE.md` §8 is explicit that Alembic is the only schema-authoring tool. `apps/api`'s Alembic migrations create `users`, `sessions`, `accounts`, `verifications` using Better Auth's documented default schema (translated to this platform's snake_case column-naming convention). `apps/web`'s Better Auth instance is configured with `modelName`/`fields` mappings pointing at those exact tables/columns — it is a *client* of Alembic's schema, never its author. This mapping is a contract: if a future Better Auth upgrade changes its default schema, `apps/web/lib/auth.ts`'s field mapping and the corresponding Alembic migration must be updated together, in the same PR (`CLAUDE.md` §9 — public/shared contract changes are versioned and documented together, not drifted apart).

**Password hashing: Argon2id via Better Auth's pluggable hash interface.** Better Auth defaults to scrypt, which its own documentation frames as the fallback "when Argon2id isn't available" — not a `CLAUDE.md` §10-compliant default (bcrypt/argon2, explicitly). `emailAndPassword.password.{hash,verify}` is overridden using the `argon2` npm package (OWASP's current recommended default, RFC 9106), called through Better Auth's own documented extension point — this is using a vetted library via a supported interface, not hand-rolled cryptography.

**OAuth: GitHub only in Phase 1.** One concrete, real provider rather than every conceivable one — `CLAUDE.md`'s no-speculative-complexity principle. Adding a second provider later is a `socialProviders` config addition, not an architecture change.

**No Better Auth "organization" plugin — workspaces/RBAC are entirely `apps/api`'s own domain.** Covered in full in ADR-0004; noted here because it is a direct consequence of choosing Better Auth: the temptation to use its bundled multi-tenancy plugin exists specifically because Better Auth ships one, and this ADR records explicitly declining it.

**Verification: JWKS fetch + cache, not a shared secret.** `apps/api` uses `PyJWKClient` (PyJWT) against Better Auth's `/api/auth/jwks`, caching the fetched key. No `BETTER_AUTH_SECRET`-equivalent value is duplicated into `apps/api`'s environment — the only cross-service coupling is the public JWKS URL and agreement on the `iss`/`aud` claims.

## Consequences

**Positive:** one Postgres system of record for identity and domain data (no eventual-consistency window between a third-party user store and our own tables); no per-MAU vendor pricing pressure; `CLAUDE.md` §10-compliant password hashing from day one; JWKS verification needs no secret rotation coordination between services.

**Negative:** every Better Auth version upgrade is a two-repository-aware change (schema mapping in `apps/web`, migration in `apps/api`), not a transparent library bump — an ongoing cost accepted as the direct consequence of the "Alembic only" rule. Self-hosting auth means this team, not a vendor, is responsible for Better Auth's own security patch cadence.

## Alternatives considered

- **Clerk.** Rejected: hosted identity store outside our own Postgres; would require webhook-driven sync to keep a local `users` row in sync, introducing exactly the eventual-consistency and dual-source-of-truth risk `CLAUDE.md` §8 argues against. Worth revisiting only if self-hosting Better Auth becomes an operational burden disproportionate to team size — not indicated at this stage.
- **Better Auth's own migration CLI, letting it own its four core tables directly.** Rejected: a second schema-authoring tool alongside Alembic, directly against `CLAUDE.md` §8's explicit "Alembic only."
- **Shared-secret HS256 JWTs.** Rejected in favor of JWKS/EdDSA — avoids a manually-synchronized secret existing in two services' environments; JWKS is Better Auth's own recommended pattern for this exact case.
- **scrypt (Better Auth's default) instead of Argon2id.** Rejected: not what `CLAUDE.md` §10 names, even though scrypt is not a weak algorithm — compliance with the constitution's explicit wording wins over "the vendor default is probably fine."
