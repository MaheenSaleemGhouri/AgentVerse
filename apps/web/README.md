# apps/web

AgentVerse's frontend — Next.js 15 (App Router), React 19, TypeScript strict, Tailwind CSS v4.

## Owned surface (Phase 0)

- Nothing product-facing yet. This app currently ships one placeholder route (`/`) and two infra routes (`/api/health`, `/api/ready`) so the Docker health-check chain and CI build stage have something real to exercise. Product routes begin in Phase 1 (`docs/roadmap.md`).
- `app/globals.css` holds primitive-tier design tokens only — see the comment at the top of that file and `docs/roadmap.md` Phase 0 for why semantic/component tokens aren't defined yet.

## Datastore

None. `apps/web` never talks to Postgres/Redis/the vector DB directly — all data access goes through `apps/api`'s `/api/v1` gateway once that contract exists (`CLAUDE.md` §5).

## Dependencies

- `@agentverse/contracts` (workspace) — not yet wired in; there's no API contract to generate types from until Phase 1.
- `apps/api` — not yet called from this app in Phase 0.

## Local development

```bash
pnpm install         # from repo root
pnpm --filter @agentverse/web dev
```

Runs at http://localhost:3000. `/api/health` and `/api/ready` are used by `infra/docker-compose.yml`'s health check for this service.

## Scripts

- `pnpm --filter @agentverse/web dev` — start the dev server (hot reload).
- `pnpm --filter @agentverse/web build` — production build.
- `pnpm --filter @agentverse/web lint` — ESLint (`next/core-web-vitals`, `next/typescript`).
- `pnpm --filter @agentverse/web typecheck` — `tsc --noEmit` against the strict base config (`../../tsconfig.base.json`).
