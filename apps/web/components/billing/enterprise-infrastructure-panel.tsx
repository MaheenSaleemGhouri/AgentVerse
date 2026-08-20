import { Rocket, Server } from "lucide-react";
import * as React from "react";

import type { Entitlements } from "@/lib/api/billing";

import { StatusBadge } from "@/components/patterns/status-badge";
import { Card } from "@/components/ui/card";

/**
 * Read-only view of the two Enterprise-tier infrastructure capabilities
 * (docs/adr/0018) — sourced from the same `/entitlements` response the
 * rest of this dashboard already fetches, so this needs no new backend
 * route. A workspace either has each capability or it doesn't; there is
 * nothing here to configure, only to see.
 */
export function EnterpriseInfrastructurePanel({
  entitlements,
}: {
  entitlements: Entitlements;
}): React.JSX.Element {
  const hasPriorityQueue = entitlements.capabilities.includes("priority_queue");
  const hasDedicatedInfrastructure = entitlements.capabilities.includes(
    "dedicated_infrastructure"
  );

  return (
    <Card className="gap-5 p-6">
      <div className="space-y-1">
        <h2 className="font-medium">Enterprise infrastructure</h2>
        <p className="text-sm text-muted-foreground">
          Dedicated worker routing for run submission (docs/adr/0018) — a plan capability, not
          something configured per workspace.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex items-start gap-3 rounded-lg border border-border p-4">
          <Rocket className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">Priority queue</span>
              <StatusBadge tone={hasPriorityQueue ? "success" : "neutral"}>
                {hasPriorityQueue ? "Active" : "Not on this plan"}
              </StatusBadge>
            </div>
            <p className="text-xs text-muted-foreground">
              Agent and workflow runs route onto a dedicated Redis stream, isolated from the
              shared fleet&apos;s contention.
            </p>
          </div>
        </div>
        <div className="flex items-start gap-3 rounded-lg border border-border p-4">
          <Server className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">Dedicated infrastructure</span>
              <StatusBadge tone={hasDedicatedInfrastructure ? "success" : "neutral"}>
                {hasDedicatedInfrastructure ? "Active" : "Not on this plan"}
              </StatusBadge>
            </div>
            <p className="text-xs text-muted-foreground">
              A worker fleet provisioned exclusively for this workspace, rather than shared
              capacity.
            </p>
          </div>
        </div>
      </div>
    </Card>
  );
}
