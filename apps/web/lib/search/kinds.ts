import type { components } from "@agentverse/contracts";

/**
 * The client-safe half of search.
 *
 * Split from `lib/api/search.ts` deliberately. That module imports
 * `apiFetch`, which is `server-only` — so a Client Component importing
 * *anything* from it, even a pure label map, drags `next/headers` into
 * the browser bundle and fails the build. Neither `tsc` nor eslint sees
 * that; only the bundler does, which is a slow way to find out.
 *
 * So everything a client needs — types, labels, link building, the
 * minimum query length — lives here, with no imports that touch the
 * server.
 */

export type SearchResults = components["schemas"]["SearchResultsOut"];
export type SearchGroup = components["schemas"]["SearchGroupOut"];
export type SearchHit = components["schemas"]["SearchHitOut"];
export type SearchKind = components["schemas"]["SearchKind"];

/**
 * Below this the API returns empty groups anyway, so the client skips
 * the round trip rather than firing one per keystroke of a word nobody
 * has finished typing. Mirrors `MIN_QUERY_LENGTH` on the server.
 */
export const MIN_SEARCH_LENGTH = 2;

/**
 * Kinds the dashboard can actually open.
 *
 * `listing` is deliberately absent. The API searches the catalog and is
 * tested doing so — the SDK and CLI already consume those results — but
 * the dashboard has no marketplace route yet (it ships with the
 * marketplace UI). A search result that navigates to a 404 is worse than
 * one that is not offered, so the palette asks only for what it can
 * open. Add `listing` here when that route exists; nothing else needs to
 * change.
 */
export const NAVIGABLE_KINDS: readonly SearchKind[] = ["agent", "knowledge_base", "team"];

/** Where a hit lives, so the palette can navigate to it. */
export function hrefForHit(workspaceId: string, kind: SearchKind, id: string): string {
  switch (kind) {
    case "agent":
      return `/dashboard/${workspaceId}/agents/${id}`;
    case "knowledge_base":
      return `/dashboard/${workspaceId}/knowledge/${id}`;
    case "team":
      return `/dashboard/${workspaceId}/teams/${id}`;
    case "listing":
      // Listings are addressed by slug, not row id — the API returns the
      // slug as the hit's `id` for exactly this reason. Unreachable from
      // the palette today; see `NAVIGABLE_KINDS`.
      return `/dashboard/${workspaceId}/marketplace/${id}`;
  }
}

export const KIND_LABELS: Record<SearchKind, string> = {
  agent: "Agents",
  knowledge_base: "Knowledge",
  team: "AI teams",
  listing: "Marketplace",
};
