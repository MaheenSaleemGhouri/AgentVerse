# Production Deployment — Vercel

## Status

`apps/web` (the Next.js frontend) is deployed to Vercel. `apps/api` and
`apps/worker` are deployed to **Render**, per `render.yaml` at the repo
root (Blueprint: `agentverse-api`, `agentverse-worker`, `agentverse-redis`,
region `oregon`). This section previously stated the backend was not
hosted anywhere — that went stale the moment the Render blueprint was
provisioned and was never updated here, which cost a real investigation
to rediscover. Verified live 2026-08-21:

- `https://agentverse-api-063d.onrender.com/health` and `/ready` → `200
  {"status":"ok","region":"primary"}`.
- `POST /mcp` → `401` (credential required, not `404`) — confirms Render
  is running current `main`, including same-day work, so auto-deploy on
  push is effectively working.
- A real signup against `https://agentverse-virid.vercel.app` returned a
  valid session, and the authenticated `/dashboard` render (which calls
  `apps/api` for the workspace list via `apiFetch`'s JWT path) rendered
  correctly — end-to-end frontend → backend → Postgres confirmed working,
  not just individually reachable.
- `/openapi.json` is `404` by design (docs disabled in production).

**Effect:** the "everything that calls apps/api will fail" warning below
is **no longer true** — dashboard data, agents, knowledge, MCP,
workflows, billing, and marketplace all go through a live backend now.

## Vercel project

- **Team:** `maheenghouris-projects`
- **Project:** `agentverse`
- **Production URL:** https://agentverse-virid.vercel.app
- **Root Directory:** `apps/web` (repo is a pnpm monorepo — Vercel must
  build from this subdirectory, not the repo root)
- **Install Command:** `cd ../.. && corepack enable && pnpm install --frozen-lockfile`
- **Build Command:** `cd ../.. && pnpm --filter @agentverse/web build`
  (both `cd ../..` because Vercel's build step runs with Root Directory
  as its cwd, and the pnpm workspace root — where `pnpm-lock.yaml` and
  `packages/contracts` live — is two levels up)

GitHub auto-deploy (push-to-deploy) is **not** connected yet — the
Vercel CLI's `git connect` could not detect the repo from this
particular sandboxed environment (a local tooling limitation, not a
project issue; plain `git` works fine here). Connect it from the Vercel
dashboard: **Project Settings → Git → Connect Git Repository** →
`MaheenSaleemGhouri/AgentVerse`, branch `main`. The Root
Directory/Install/Build Command settings above are already saved on the
project and will apply to those builds too.

## Database

Production Postgres is provisioned via **Vercel's Neon integration**
(`neon-cinnabar-envelope`), connected to the `agentverse` project.
`DATABASE_URL` (and the Neon-provided variants) are set for
Production/Preview/Development automatically by the integration.

Alembic migrations run against it whenever Render redeploys `apps/api`
(same Neon database, reused by both services — see `render.yaml`'s
top-of-file comment). The `b6e2f04a9d17` head this doc previously cited
is stale; the live `/mcp` route responding `401` rather than `404`
(instead of the pre-Phase-12 behavior) confirms the schema is at least
current through this session's migrations. Re-verify with `alembic
current` against the real `AGENTVERSE_API_DATABASE_URL` before trusting a
specific revision number here rather than re-guessing. Test signup rows
(`prod-smoke-*@example.com`, `live-check-*@example.com`) are left in
place as evidence the auth loop works end-to-end — safe to delete
whenever.

## Environment variables (production scope)

| Variable | Category | Status |
|---|---|---|
| `DATABASE_URL` | SECRET, REQUIRED | Set (Neon integration) |
| `BETTER_AUTH_SECRET` | SECRET, REQUIRED | Set (generated) |
| `BETTER_AUTH_URL` | SERVER-ONLY, REQUIRED | Set — `https://agentverse-virid.vercel.app` |
| `NEXT_PUBLIC_BETTER_AUTH_URL` | PUBLIC, REQUIRED | Set — same value as above (this is intentionally public: it's just the app's own URL) |
| `INTERNAL_API_SECRET` | SECRET, REQUIRED | Set — must equal Render's `AGENTVERSE_API_INTERNAL_API_SECRET` byte-for-byte (`render.yaml`'s own comment on that var). Not independently re-verified this pass since neither platform exposes the plaintext value via the tooling available; if `/internal/*` calls ever start 401ing, this pairing is the first thing to check. |
| `API_INTERNAL_URL` | SERVER-ONLY, REQUIRED | Set — `https://agentverse-api-063d.onrender.com` (Render's assigned hostname; the `agentverse-api.onrender.com` name predicted in `render.yaml`'s comment was already taken, so Render appended a suffix) |
| `API_PUBLIC_URL` | SERVER-ONLY, OPTIONAL | SCIM discovery only — check if a customer relies on it before assuming unset is fine |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | SECRET, OPTIONAL | Not set — GitHub login button stays hidden until both are set (by design, never a dead button) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | SECRET, OPTIONAL | Not set — same as above for Google |

`OPENAI_API_KEY` is **not** a variable `apps/web` reads at all — it belongs
to `apps/api`'s environment, to be set wherever that service ends up
hosted, not in this Vercel project.

## Domain

- `agentverse.com`, `agentverse.ai`, `agentverse.dev` are all already
  registered by other parties — not available.
- `getagentverse.com`, `useagentverse.com`, `agentversehq.com` show no
  DNS record (likely available, unverified against a registrar).
- No custom domain has been purchased or attached. Production currently
  serves on Vercel's own domain: `agentverse-virid.vercel.app`.

## Known non-blocking issue

`/pricing` still logs a "page changed from static to dynamic at runtime"
warning on every request, and `loadSsoProviders` logs "could not reach
apps/api" even though the backend is now reachable. Re-diagnosed
2026-08-21: the backend is not actually unreachable — `lib/sso-providers.ts`
calls `fetch(..., { cache: "no-store" })` from `lib/auth.ts`'s top-level
await, and Next.js's own internal `DYNAMIC_SERVER_USAGE` bailout signal
(thrown to abort static prerendering of `/pricing`) gets caught by that
function's generic `try/catch` and misreported as a fetch failure — it is
not evidence of a real connectivity problem. Effect is still harmless
(SSO provider list is empty on affected renders, password/social login
unaffected, page still returns 200) — but the log message is misleading
and worth narrowing to a real `fetch`-vs-framework-signal distinction if
anyone chases it again.

## Next steps

1. Confirm the exact Alembic revision Render's `apps/api` is running
   (`alembic current` against the real `AGENTVERSE_API_DATABASE_URL`) and
   record it here instead of the stale number this doc previously had.
2. Connect GitHub → Vercel via the dashboard for push-to-deploy, if not
   already connected (not re-verified this pass).
3. Decide on a custom domain from the available-alternatives list above,
   or accept the `.vercel.app`/`.onrender.com` domains for now.
4. Delete the `prod-smoke-*@example.com` / `live-check-*@example.com`
   test accounts once no longer needed as verification references.
5. Narrow `loadSsoProviders`'s catch block so a real fetch failure and
   Next.js's `DYNAMIC_SERVER_USAGE` signal aren't logged identically
   (see "Known non-blocking issue" above).
