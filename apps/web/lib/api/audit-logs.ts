import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";

/**
 * Every type below is generated from the API's OpenAPI schema — never
 * hand-written, so a backend field rename fails the build here rather
 * than becoming `undefined` at runtime.
 */
export type AuditLogEntry = components["schemas"]["AuditLogResponse"];
export type AuditLogPage = components["schemas"]["AuditLogPage"];

export interface AuditLogFilters {
  action?: string;
  actor_user_id?: string;
  cursor?: string;
  limit?: number;
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
