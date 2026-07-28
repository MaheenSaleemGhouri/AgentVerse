"use client";

import { Activity, Ban } from "lucide-react";
import * as React from "react";

import { formatRelativeTime } from "@/lib/format";
import { CALL_STATUS } from "@/lib/integrations-vocabulary";
import { useIntegrationMetrics, useToolCalls } from "@/lib/queries/integrations";
import { cn } from "@/lib/utils";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { StatCard } from "@/components/patterns/stat-card";
import { StatusBadge } from "@/components/patterns/status-badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

const STATUS_FILTERS = [
  { value: "all", label: "All" },
  { value: "success", label: "Success" },
  { value: "error", label: "Failed" },
  { value: "denied", label: "Denied" },
  { value: "timeout", label: "Timed out" },
] as const;

/**
 * Tool-call execution history and metrics.
 *
 * Denied calls are first-class here rather than filtered out: a blocked
 * SSRF attempt or a refused write is the audit trail this phase's
 * controls exist to produce, and hiding it would waste most of their
 * value.
 */
export function RuntimeView({
  workspaceId,
  installedServerId,
}: {
  workspaceId: string;
  installedServerId?: string;
}): React.JSX.Element {
  const [status, setStatus] = React.useState<string>("all");
  const metrics = useIntegrationMetrics(workspaceId, installedServerId);
  const calls = useToolCalls(workspaceId, {
    installedServerId,
    ...(status === "all" ? {} : { status }),
  });

  if (calls.isError) {
    return (
      <ErrorState
        title="Could not load execution history"
        description="The orchestration service did not respond. Past calls are unaffected."
        onRetry={() => void calls.refetch()}
      />
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Calls"
          value={metrics.data ? String(metrics.data.total_calls) : "—"}
        />
        <StatCard
          label="Failed"
          value={metrics.data ? String(metrics.data.failed_calls) : "—"}
        />
        <StatCard
          label="Denied"
          value={metrics.data ? String(metrics.data.denied_calls) : "—"}
        />
        <StatCard
          label="p95 latency"
          value={metrics.data ? `${metrics.data.p95_duration_ms}ms` : "—"}
        />
      </div>

      {metrics.data && metrics.data.denied_calls > 0 && (
        <p className="flex items-center gap-2 rounded-md border border-warning/30 bg-warning-soft px-3 py-2 text-sm">
          <Ban className="size-4 shrink-0 text-warning" aria-hidden="true" />
          <span>
            {metrics.data.denied_calls} call
            {metrics.data.denied_calls === 1 ? " was" : "s were"} refused. That is the permission
            and egress controls working — open one to see which rule applied.
          </span>
        </p>
      )}

      <Tabs value={status} onValueChange={setStatus}>
        <TabsList>
          {STATUS_FILTERS.map((filter) => (
            <TabsTrigger key={filter.value} value={filter.value}>
              {filter.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {calls.isLoading && !calls.data ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }, (_, index) => (
            <Skeleton key={index} className="h-16 rounded-lg" />
          ))}
        </div>
      ) : (calls.data?.data ?? []).length === 0 ? (
        <EmptyState
          icon={Activity}
          title="No tool calls yet"
          description="Every call an agent makes through an integration is recorded here — including ones that were refused."
        />
      ) : (
        <ol className="flex flex-col gap-2">
          {(calls.data?.data ?? []).map((call) => {
            const meta = CALL_STATUS[call.status];
            const Icon = meta.icon;
            const isRefused = call.status === "denied" || call.status === "circuit_open";

            return (
              <li
                key={call.id}
                className={cn(
                  "rounded-lg border p-3",
                  call.status === "error" || call.status === "timeout"
                    ? "border-destructive/30 bg-destructive-soft/30"
                    : isRefused
                      ? "border-warning/30 bg-warning-soft/30"
                      : "border-border"
                )}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <code className="font-mono text-sm">{call.tool_name}</code>
                  <StatusBadge tone={meta.tone}>{meta.label}</StatusBadge>
                  {call.attempt > 1 && (
                    <span className="text-xs text-muted-foreground">
                      attempt {call.attempt}
                    </span>
                  )}
                  <span className="ml-auto text-xs text-muted-foreground">
                    {call.duration_ms !== null ? `${call.duration_ms}ms · ` : ""}
                    {formatRelativeTime(call.created_at)}
                  </span>
                </div>

                {call.denial_reason && (
                  <p className="mt-1.5 text-sm">
                    <span className="text-muted-foreground">Refused: </span>
                    {call.denial_reason}
                  </p>
                )}
                {call.error_message && (
                  <p className="mt-1.5 text-sm">
                    <span className="text-muted-foreground">Error: </span>
                    {call.error_message}
                  </p>
                )}

                <Collapsible>
                  <CollapsibleTrigger className="mt-1.5 text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground">
                    Arguments and result
                  </CollapsibleTrigger>
                  <CollapsibleContent className="mt-2 flex flex-col gap-2">
                    <div>
                      <p className="text-xs text-muted-foreground">Arguments</p>
                      <pre className="mt-1 overflow-x-auto rounded-md bg-muted/50 p-2 font-mono text-xs">
                        {JSON.stringify(call.arguments, null, 2)}
                      </pre>
                    </div>
                    {call.result_preview && (
                      <div>
                        <p className="text-xs text-muted-foreground">
                          Result preview
                          {call.result_bytes !== null
                            ? ` · ${call.result_bytes} bytes returned`
                            : ""}
                        </p>
                        <pre className="mt-1 max-h-48 overflow-auto rounded-md bg-muted/50 p-2 font-mono text-xs whitespace-pre-wrap">
                          {call.result_preview}
                        </pre>
                      </div>
                    )}
                  </CollapsibleContent>
                </Collapsible>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
