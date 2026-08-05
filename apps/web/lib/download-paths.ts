/**
 * URLs for this app's own download route handlers.
 *
 * Deliberately *not* under `lib/api/`. Everything there talks to
 * apps/api and therefore imports `lib/api/client.ts`, which is
 * `server-only` — importing any value from those modules into a client
 * component pulls `server-only` and `next/headers` into the browser
 * bundle and fails the production build. Client components may import
 * *types* from `lib/api/*` (erased at compile time) and call server
 * actions from `lib/api/actions.ts`; a plain function they need at
 * runtime belongs here instead.
 *
 * These paths point at route handlers in `app/downloads/**`, which
 * authenticate the session, call apps/api server-side with its bearer
 * token, and stream the response back with `Content-Disposition`
 * intact — so the browser saves a file rather than buffering a blob,
 * and apps/api stays internal-only (CLAUDE.md §5).
 */

export interface AuditExportFilters {
  action?: string;
  actor_user_id?: string;
}

export function auditExportPath(
  workspaceId: string,
  format: "csv" | "json",
  filters: AuditExportFilters = {}
): string {
  const params = new URLSearchParams({ format });
  if (filters.action) params.set("action", filters.action);
  if (filters.actor_user_id) params.set("actor_user_id", filters.actor_user_id);
  return `/downloads/audit-logs/${workspaceId}?${params.toString()}`;
}
