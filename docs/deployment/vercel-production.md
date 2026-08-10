# Production Deployment — Vercel

## Status

`apps/web` (the Next.js frontend) is deployed to Vercel. `apps/api` and
`apps/worker` are **not** deployed anywhere yet — Vercel cannot run them
(they are a long-running FastAPI service and a background worker fleet,
not serverless functions), and no separate host (Railway/Coolify/Fly) has
been configured. This was an explicit, agreed scope decision, not an
oversight.

**Effect:** authentication (signup/login/logout/password reset) works in
production — Better Auth runs inside `apps/web` against its own Postgres
connection. Everything that calls `apps/api` (dashboard data, agents,
knowledge, MCP, workflows, billing, marketplace) will fail until a
backend is hosted and `API_INTERNAL_URL` is pointed at it.

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

All Alembic migrations have been run against it — the schema matches
`apps/api`'s current head revision (`b6e2f04a9d17`). No seed/fixture data
was inserted; the one row present is a real smoke-test signup
(`prod-smoke-*@example.com`), left in place as evidence the auth loop
works end-to-end — safe to delete whenever.

## Environment variables (production scope)

| Variable | Category | Status |
|---|---|---|
| `DATABASE_URL` | SECRET, REQUIRED | Set (Neon integration) |
| `BETTER_AUTH_SECRET` | SECRET, REQUIRED | Set (generated) |
| `BETTER_AUTH_URL` | SERVER-ONLY, REQUIRED | Set — `https://agentverse-virid.vercel.app` |
| `NEXT_PUBLIC_BETTER_AUTH_URL` | PUBLIC, REQUIRED | Set — same value as above (this is intentionally public: it's just the app's own URL) |
| `INTERNAL_API_SECRET` | SECRET, REQUIRED | Set (generated) — **must be regenerated and set identically on apps/api** once it's hosted; don't reuse this value blindly |
| `API_INTERNAL_URL` | SERVER-ONLY, REQUIRED | Placeholder (`https://backend-not-yet-deployed.invalid`) — replace with the real backend URL once hosted, then redeploy |
| `API_PUBLIC_URL` | SERVER-ONLY, OPTIONAL | Not set (SCIM discovery only; unneeded until backend exists) |
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

`/pricing` logs an "page changed from static to dynamic at runtime"
warning on every request. Cause: the page attempts to fetch SSO provider
config from `apps/api` (`revalidate: 0`), which fails since the backend
isn't hosted; Next.js flags the static/dynamic mismatch this produces.
The page still renders correctly (200, no user-visible effect) — this is
log noise tied directly to the "no backend yet" state, and should
resolve on its own once `API_INTERNAL_URL` points at a real service.

## Next steps

1. Host `apps/api` + `apps/worker` (Railway/Coolify/Fly per `CLAUDE.md`
   §12), set `API_INTERNAL_URL` to its real URL, generate a fresh
   `INTERNAL_API_SECRET` shared by both sides, set `OPENAI_API_KEY` and
   the rest of `apps/api/.env.example`'s required keys there.
2. Connect GitHub → Vercel via the dashboard for push-to-deploy.
3. Decide on a custom domain from the available-alternatives list above,
   or accept the `.vercel.app` domain for now.
4. Delete the `prod-smoke-*@example.com` test account once no longer
   needed as a verification reference.
