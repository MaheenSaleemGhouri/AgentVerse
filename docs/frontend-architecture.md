# Frontend Architecture Conventions

Owned by `senior-frontend-engineer` (CLAUDE.md §6, §18.1). This doc records conventions established in `apps/web` as they're introduced — read it before introducing a new one; a second, competing way to do the same thing is a defect, not a style choice.

## Data access

- **Server Components fetch initial data** via `lib/api/<domain>.ts` (server-only, `apiFetch` in `lib/api/client.ts` — resolves the session to a bearer token via `next/headers`, throws `ApiError` with a `.status` on non-2xx). Pages pass results down as props.
- **Client-triggered mutations** go through `"use server"` wrappers in `lib/api/actions.ts` — `apiFetch` needs `next/headers` and cannot be called from a Client Component directly; these thin wrappers are the bridge (established Phase 1, extended Phase 4 for agents).
- **TanStack Query** (`app/providers.tsx`, installed Phase 4 M5) is used for its `useMutation` — wrapping a Server Action to get loading/error/success state on a button (see `components/agents/agent-config-panel.tsx`, `agent-builder.tsx`). Page-level reads stay Server-Component-first per `nextjs-expert`'s own rule ("fetch as close to where it's rendered as possible"); we do not run a parallel client cache for data a Server Component already fetched — a mutation's success calls `router.refresh()` to re-fetch server-side rather than manually patching a query cache. Introduce `useQuery` only when a surface genuinely needs client-side background refetch/polling that a Server Component re-render can't satisfy.
- **Zustand** is reserved for ephemeral, session-scoped UI state that has no server representation — e.g. `lib/stores/agent-builder-store.ts` (active config tab, dirty flag). Never put server-originated data (agent config, run history) in a Zustand store. Every builder-session store exposes a `reset()` called on unmount so state never leaks into the next session.

## Streaming (SSE) from the browser

Native `EventSource` cannot set an `Authorization` header. Any backend SSE route that requires bearer auth needs a same-origin Next.js Route Handler proxy: it resolves the browser's session cookie server-side (`getBearerToken()` from `lib/api/client.ts`), attaches the bearer token to the upstream fetch, and pipes the response body straight through. See `app/api/runs/[runId]/stream/route.ts` and `lib/hooks/useAgentRunStream.ts` (docs/adr/0007's addendum). Follow this pattern for any future SSE/streaming consumer rather than exposing a bearer token to client-side JS.

High-frequency stream events are buffered in a `ref` and flushed to React state on an interval (never `setState` per event) — see `useAgentRunStream`'s 150ms flush.

## Testing

Vitest + `@testing-library/react` (`vitest.config.ts`, jsdom environment), introduced Phase 4 M7. `pnpm test` runs `vitest run`, wired into CI's `node-checks` job for `@agentverse/web` only (the contracts package has no test script). Test pure logic (Zod schemas, hooks) directly; mock browser-only APIs (`EventSource`) that jsdom doesn't implement via `vi.stubGlobal`.

## App shell

`components/dashboard/sidebar.tsx` is the fixed AVDS sidebar (Dashboard/Agents/Knowledge/MCP/Workflows/Analytics/Team/Billing/Settings), rendered by `app/(dashboard)/dashboard/[workspaceId]/layout.tsx` once a workspace is selected. Sections without a shipped page yet render disabled with a "Soon" badge rather than a dead link or being omitted — add the real `href` and drop `comingSoon` the same PR a section's page ships.
