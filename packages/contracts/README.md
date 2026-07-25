# @agentverse/contracts

Shared TypeScript contracts for AgentVerse, generated from `apps/api`'s OpenAPI schema.

## Owned surface

- **Generated types** for every `/api/v1` request/response shape, and for SSE/WebSocket event payloads, once those exist.
- Nothing in `src/` outside `version.ts` is hand-authored — see `CLAUDE.md` §6: "Generated OpenAPI types live in `lib/api/types/generated.ts`, regenerated not hand-edited."

## Current state (Phase 1)

`src/generated.ts` is generated from `apps/api/openapi.json` (a checked-in, static export of the live OpenAPI schema — regenerated via `uv run python -c "..."`, see `apps/api/README.md`). Covers `/api/v1/workspaces` and `/api/v1/workspaces/{workspace_id}/api-keys`.

## Dependencies

- Consumed by: `apps/web` (`lib/api/`).
- Generated from: `apps/api`'s OpenAPI schema (owner: `api-designer`).

## Scripts

- `pnpm --filter @agentverse/contracts run generate` — regenerate `src/generated.ts` from `../../apps/api/openapi.json`. Run this (and commit the diff) whenever `apps/api`'s routes or Pydantic schemas change; regenerate `apps/api/openapi.json` itself first (see `apps/api/README.md`).
- `pnpm --filter @agentverse/contracts build` — compile to `dist/`.
- `pnpm --filter @agentverse/contracts typecheck` — type-check only.
