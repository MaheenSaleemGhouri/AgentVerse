import type { components } from "@agentverse/contracts";

import { apiFetch } from "@/lib/api/client";

export type GrowthMetrics = components["schemas"]["GrowthMetricsResponse"];

/**
 * Referral and marketplace growth-funnel counts for one workspace
 * (Phase 11) — feeds the Analytics page's Growth section.
 */
export async function getGrowthMetrics(workspaceId: string): Promise<GrowthMetrics> {
  return apiFetch<GrowthMetrics>(`/api/v1/workspaces/${workspaceId}/growth/metrics`);
}
