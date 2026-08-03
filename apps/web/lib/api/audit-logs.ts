import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";

/**
 * Every type below is generated from the API's OpenAPI schema — never
 * hand-written, so a backend field rename fails the build here rather
 * than becoming `undefined` at runtime.
 */
export type AuditLogEntry = components["schemas"]["AuditLogResponse"];
export type AuditLogPage = components["schemas"]["AuditLogPage"];
export type AuditActivity = components["schemas"]["AuditActivityResponse"];

export interface AuditLogFilters {
  action?: string;
  actor_user_id?: string;
  cursor?: string;
  limit?: number;
}

export async function getAuditActivity(
  workspaceId: string,
  days = 30
): Promise<AuditActivity> {
  return apiFetch<AuditActivity>(
    `/api/v1/workspaces/${workspaceId}/audit-logs/activity?days=${days}`
  );
}

/**
 * The download URL for an export — a route on *this* app, not on
 * apps/api.
 *
 * apps/api is internal-only and bearer-authenticated server-side
 * (CLAUDE.md §5: the frontend never talks to internal services
 * directly, and the browser has no token to present). The route handler
 * at this path authenticates, calls apps/api, and streams the result
 * back with its `Content-Disposition` intact, so the file still lands
 * on disk as a download rather than being buffered into a JS blob.
 */
export function auditExportPath(
  workspaceId: string,
  format: "csv" | "json",
  filters: Pick<AuditLogFilters, "action" | "actor_user_id"> = {}
): string {
  const params = new URLSearchParams({ format });
  if (filters.action) params.set("action", filters.action);
  if (filters.actor_user_id) params.set("actor_user_id", filters.actor_user_id);
  return `/downloads/audit-logs/${workspaceId}?${params.toString()}`;
}

export async function listAuditLogs(
  workspaceId: string,
  filters: AuditLogFilters = {}
): Promise<AuditLogPage> {
  const params = new URLSearchParams();
  if (filters.action) params.set("action", filters.action);
  if (filters.actor_user_id) params.set("actor_user_id", filters.actor_user_id);
  if (filters.cursor) params.set("cursor", filters.cursor);
  if (filters.limit) params.set("limit", String(filters.limit));
  const query = params.toString();
  return apiFetch<AuditLogPage>(
    `/api/v1/workspaces/${workspaceId}/audit-logs${query ? `?${query}` : ""}`
  );
}
