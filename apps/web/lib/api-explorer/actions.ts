"use server";

import { ApiError, apiFetch } from "@/lib/api/client";
import { EXPLORER_ENDPOINTS, buildPath } from "@/lib/api-explorer/endpoints";

export interface ExplorerResult {
  ok: boolean;
  status: number;
  /** Pretty-printed JSON, or the raw error text the API returned. */
  body: string;
  /** Milliseconds, measured server-side around the upstream call. */
  durationMs: number;
}

/**
 * Execute one catalogued endpoint against the API.
 *
 * **The client sends an endpoint id, never a path.** The path is rebuilt
 * here from the server's own copy of the catalog, so this action cannot
 * be used to proxy an arbitrary URL with the caller's bearer token — an
 * explorer that forwarded a client-supplied path would be a
 * request-forgery primitive pointed at our own internal API, reachable
 * by anyone with a session.
 *
 * Parameter *values* still come from the client, which is fine: they are
 * URL-encoded into a path shape the server chose, and the API enforces
 * its own authorization on the result. A caller cannot see anything here
 * they could not already see with their own API key.
 */
export async function sendExplorerRequest(
  workspaceId: string,
  endpointId: string,
  pathValues: Record<string, string>,
  queryValues: Record<string, string>,
): Promise<ExplorerResult> {
  const endpoint = EXPLORER_ENDPOINTS.find((candidate) => candidate.id === endpointId);
  if (!endpoint) {
    return { ok: false, status: 400, body: "Unknown endpoint.", durationMs: 0 };
  }

  const path = buildPath(endpoint, workspaceId, pathValues, queryValues);
  const startedAt = Date.now();

  try {
    const result = await apiFetch<unknown>(path);
    return {
      ok: true,
      status: 200,
      body: JSON.stringify(result, null, 2),
      durationMs: Date.now() - startedAt,
    };
  } catch (error) {
    if (error instanceof ApiError) {
      // The API's own error envelope is the useful thing here — it
      // carries the stable `code` and the `request_id` a customer would
      // quote in support. Showing it verbatim beats paraphrasing it.
      return {
        ok: false,
        status: error.status,
        body: error.message,
        durationMs: Date.now() - startedAt,
      };
    }
    throw error;
  }
}
