# @agentverse/contracts

Shared TypeScript contracts for AgentVerse, generated from `apps/api`'s OpenAPI schema.

## Owned surface

- **Generated types** for every `/api/v1` request/response shape, and for SSE/WebSocket event payloads, once those exist.
- Nothing in `src/` outside `version.ts` is hand-authored — see `CLAUDE.md` §6: "Generated OpenAPI types live in `lib/api/types/generated.ts`, regenerated not hand-edited."

## Current state (Phase 0)

`apps/api` exposes only `/health` and `/ready` in this phase — there is no resource schema to generate yet. This package exists now so `apps/web` and `apps/api` have a real shared-types dependency wired through the workspace from the first commit, rather than retrofitting it once Phase 1 lands the first real API contract.

## Dependencies

- Consumed by: `apps/web` (`lib/api/`).
- Generated from: `apps/api`'s OpenAPI schema (owner: `api-designer`).

## Scripts

- `pnpm --filter @agentverse/contracts build` — compile to `dist/`.
- `pnpm --filter @agentverse/contracts typecheck` — type-check only.
