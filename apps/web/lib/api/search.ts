import { apiFetch } from "@/lib/api/client";
import type { SearchKind, SearchResults } from "@/lib/search/kinds";

/**
 * The server half of search.
 *
 * `apiFetch` is `server-only`, so nothing in a Client Component may
 * import this module — not even for a type. The client-safe pieces
 * (types, labels, link building) live in `lib/search/kinds.ts`, and the
 * palette reaches this function through a Server Action.
 */
export async function searchWorkspace(
  workspaceId: string,
  query: string,
  kinds?: readonly SearchKind[],
): Promise<SearchResults> {
  const params = new URLSearchParams({ q: query });
  for (const kind of kinds ?? []) params.append("kinds", kind);
  return apiFetch<SearchResults>(
    `/api/v1/workspaces/${workspaceId}/search?${params.toString()}`,
  );
}
