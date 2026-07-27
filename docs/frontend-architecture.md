# Frontend Architecture Conventions

Owned by `senior-frontend-engineer` (CLAUDE.md §6, §18.1). This doc records conventions established in `apps/web` as they're introduced — read it before introducing a new one; a second, competing way to do the same thing is a defect, not a style choice.

## Data access

- **Server Components fetch initial data** via `lib/api/<domain>.ts` (server-only, `apiFetch` in `lib/api/client.ts` — resolves the session to a bearer token via `next/headers`, throws `ApiError` with a `.status` on non-2xx). Pages pass results down as props.
- **Client-triggered mutations** go through `"use server"` wrappers in `lib/api/actions.ts` — `apiFetch` needs `next/headers` and cannot be called from a Client Component directly; these thin wrappers are the bridge (established Phase 1, extended Phase 4 for agents).
- **TanStack Query** (`app/providers.tsx`) covers both mutations and the client-side reads that need background refetch, filtering, or polling. **Updated in the UI Sprint** from the earlier "mutations only" rule: several surfaces (agents list filtering, document ingestion polling, members table) genuinely need a client cache, so the pattern is now:
  - The Server Component still fetches for first paint and passes the result as `initialData` into the hook — so there is no loading flash for data the page already had.
  - Hooks live in `lib/queries/<domain>.ts` and call the read Server Actions in `lib/api/actions.ts`. Components never call an action directly.
  - Query keys come **only** from the factory in `lib/queries/keys.ts`, workspace-scoped first. Inline key literals are a defect — an invalidation that misses because two call sites spelled a key differently is silent.
  - Mutations invalidate via those same keys rather than `router.refresh()`.
  - Default `staleTime` is 30s (set on the QueryClient); per-hook overrides where data is more volatile. `useDocuments` polls at 3s while any document is still ingesting and stops once all have settled.
- **Zustand** is reserved for ephemeral, session-scoped UI state that has no server representation — e.g. `lib/stores/agent-builder-store.ts` (active config tab, dirty flag). Never put server-originated data (agent config, run history) in a Zustand store. Every builder-session store exposes a `reset()` called on unmount so state never leaks into the next session.

## Streaming (SSE) from the browser

Native `EventSource` cannot set an `Authorization` header. Any backend SSE route that requires bearer auth needs a same-origin Next.js Route Handler proxy: it resolves the browser's session cookie server-side (`getBearerToken()` from `lib/api/client.ts`), attaches the bearer token to the upstream fetch, and pipes the response body straight through. See `app/api/runs/[runId]/stream/route.ts` and `lib/hooks/useAgentRunStream.ts` (docs/adr/0007's addendum). Follow this pattern for any future SSE/streaming consumer rather than exposing a bearer token to client-side JS.

High-frequency stream events are buffered in a `ref` and flushed to React state on an interval (never `setState` per event) — see `useAgentRunStream`'s 150ms flush, and `useTeamSessionStream`'s (Phase 9), where a parallel topology emits from several members at once.

**Open unions on the wire.** `execution_events.event_type` is deliberately free-form text on the backend — the vocabulary grows per topology and adding one must never require a migration. The TypeScript union in `useTeamSessionStream.ts` is therefore the enforcement point: the renderer is exhaustive over it with a `never` check, so a new backend event type fails the build until handled. `toTeamEvent()` narrows wire events into that union and maps anything unrecognised to a labelled `unknown_event` — the one case that cannot be a build error is an older frontend deployed against a newer API mid-rollout, and it must label what it cannot render rather than dropping it.

**Live and finished must render identically.** A session in flight is fed from SSE; a finished one reads the durable `/events` endpoint through the *same* narrowing function. Two separate narrowings would be two chances to disagree. A finished session never opens a stream that will never receive anything.

## Testing

Vitest + `@testing-library/react` (`vitest.config.ts`, jsdom environment), introduced Phase 4 M7. `pnpm test` runs `vitest run`, wired into CI's `node-checks` job for `@agentverse/web` only (the contracts package has no test script). Test pure logic (Zod schemas, hooks) directly; mock browser-only APIs (`EventSource`) that jsdom doesn't implement via `vi.stubGlobal`.

## App shell

Rebuilt in the UI Sprint. `app/(dashboard)/dashboard/[workspaceId]/layout.tsx` renders `components/shell/topbar.tsx` + `components/shell/sidebar.tsx` around every workspace route; the session and workspace list are fetched there once and passed down, so the shell is complete on first paint.

**One navigation model.** `lib/navigation.ts` is the single source for routes — the sidebar, the ⌘K command palette, and the breadcrumb builder all read from it. Adding a route in one place makes it navigable, searchable, and correctly labelled everywhere. Three hand-maintained copies of that list is exactly the drift Rule 3 exists to prevent.

`hiddenFromSidebar` keeps deep routes (Documents, Upload, API keys, Security, Audit logs) out of the fixed nine-section AVDS sidebar while leaving them routable and palette-searchable.

## Component layers

- `components/ui/` — shadcn primitives only, themed to AVDS tokens. No product logic.
- `components/patterns/` — cross-domain building blocks used by every screen: `PageHeader`, `EmptyState`, `ErrorState`, `StatCard`, `StatusBadge`, `CopyButton`, `IntegrationPending`.
- `components/<domain>/` — product components (`agents/`, `knowledge/`, `playground/`, `teams/`, `team/`, `settings/`, `shell/`, `dashboard/`).

> `teams/` and `team/` are not a typo. `teams/` is multi-agent teams; `team/` is human workspace membership. The sidebar labels the latter **Members** for the same reason — two entries both reading "Team" would be a coin flip for the user every time. They share no route, hook, or API module.

Anything with more than one visual state exposes `cva` variants with a typed props interface, never assembled class strings.

## Unbacked surfaces

`lib/feature-availability.ts` is the registry of screens whose backend has not shipped. Those screens render `<IntegrationPending feature="…" />`, which states the capability, the exact endpoints it will call, and the roadmap phase that delivers them.

**Never fabricate data for these.** A dashboard showing invented revenue or a plausible-looking latency curve silently misinforms; a panel that names what it is waiting on is honest and doubles as the integration checklist. When a phase lands, delete the registry entry — any leftover pending panel then fails the build, because its key no longer exists.

## Performance

`framer-motion` is loaded only by the builder canvas, via `next/dynamic` with a height-matched skeleton, so dashboard/knowledge/settings routes never pay for animation weight they don't render.
