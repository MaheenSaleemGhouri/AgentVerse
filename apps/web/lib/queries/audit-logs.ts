"use client";

import { useQuery } from "@tanstack/react-query";

import { listAuditLogsAction } from "@/lib/api/actions";
import type { AuditLogFilters, AuditLogPage } from "@/lib/api/audit-logs";
import { queryKeys } from "@/lib/queries/keys";

export function useAuditLogs(
  workspaceId: string,
  filters: AuditLogFilters = {},
  initialData?: AuditLogPage
) {
  return useQuery({
    queryKey: queryKeys.auditLogs(workspaceId, {
      action: filters.action,
      actor_user_id: filters.actor_user_id,
    }),
    queryFn: () => listAuditLogsAction(workspaceId, { ...filters, limit: 50 }),
    // Only the unfiltered first page has a server-fetched initial
    // value — an `initialData` for every possible filter combination
    // would need to be re-derived client-side anyway, so filtered
    // queries just fetch normally.
    ...(!filters.action && !filters.actor_user_id && initialData ? { initialData } : {}),
  });
}
