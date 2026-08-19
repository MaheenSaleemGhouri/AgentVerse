"use client";

import { CheckCircle2, Loader2, ShieldQuestion, XCircle } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import type { WorkflowNode, WorkflowNodeRun } from "@/lib/api/workflows";
import { useResolveWorkflowApproval, useWorkflowRun, useWorkflowRunNodes } from "@/lib/queries/workflows";
import { WORKFLOW_NODE_META } from "@/lib/workflows/node-types";
import { cn } from "@/lib/utils";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

function formatMicroUsd(microUsd: number): string {
  return `$${(microUsd / 1_000_000).toFixed(4)}`;
}

const NODE_RUN_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  queued: Loader2,
  running: Loader2,
  paused_for_approval: ShieldQuestion,
  success: CheckCircle2,
  error: XCircle,
  cancelled: XCircle,
  skipped: CheckCircle2,
};

function nodeRunSummary(nodeRun: WorkflowNodeRun, node: WorkflowNode | undefined): string {
  const label = node ? WORKFLOW_NODE_META[node.type].label : "Step";
  switch (nodeRun.status) {
    case "queued":
      return `${label} — queued`;
    case "running":
      return `${label} — running`;
    case "paused_for_approval":
      return `${label} — waiting for approval`;
    case "success":
      return `${label} — completed`;
    case "error":
      return `${label} — failed`;
    case "cancelled":
      return `${label} — cancelled`;
    case "skipped":
      return `${label} — skipped`;
    default:
      return label;
  }
}

/**
 * Per-node DAG run status, polled (docs/adr/0016: no SSE stream for
 * workflow runs this phase — nodes complete on the order of seconds-to-
 * minutes, so polling already satisfies "what is happening right now").
 * Visual language mirrors `RunTraceViewer`'s step list; the content
 * differs because a DAG run's unit is a node, not a token-level step.
 */
export function WorkflowRunStatus({
  workspaceId,
  workflowId,
  runId,
  nodesById,
  showFullRunLink = false,
}: {
  workspaceId: string;
  workflowId: string;
  runId: string;
  nodesById: Map<string, WorkflowNode>;
  /** Set from `RunWorkflowTrigger`'s inline preview; the run-detail page itself omits a self-link. */
  showFullRunLink?: boolean;
}): React.JSX.Element {
  const { data: run, isLoading: runLoading } = useWorkflowRun(workspaceId, workflowId, runId);
  const { data: nodeRuns } = useWorkflowRunNodes(workspaceId, workflowId, runId, run?.status);
  const resolveApproval = useResolveWorkflowApproval(workspaceId, workflowId, runId);

  const lastNodeRun = nodeRuns?.at(-1);

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium">
          {runLoading || !run || run.status === "queued" || run.status === "running" ? (
            <Loader2 className="size-4 animate-spin text-primary" />
          ) : run.status === "error" || run.status === "cancelled" ? (
            <XCircle className="size-4 text-destructive" />
          ) : run.status === "paused" ? (
            <ShieldQuestion className="size-4 text-warning" />
          ) : (
            <CheckCircle2 className="size-4 text-success" />
          )}
          Run {runId.slice(0, 8)}
        </div>
        <div className="flex items-center gap-3">
          {showFullRunLink && (
            <Link
              href={`/dashboard/${workspaceId}/workflows/${workflowId}/runs/${runId}`}
              className="text-xs font-medium text-primary hover:underline"
            >
              View full run
            </Link>
          )}
          {run && (
            <span className="font-mono text-sm tabular-nums text-muted-foreground">
              {formatMicroUsd(run.cost_micro_usd ?? 0)}
            </span>
          )}
        </div>
      </div>

      <p aria-live="polite" className="sr-only">
        {lastNodeRun ? nodeRunSummary(lastNodeRun, nodesById.get(lastNodeRun.node_id)) : "Waiting for the run to start"}
      </p>

      {run?.error_message && (
        <p className="rounded-md bg-destructive-soft px-2 py-1.5 text-sm text-destructive-strong">
          {run.error_message}
        </p>
      )}

      <ol className="flex max-h-80 flex-col gap-1.5 overflow-y-auto">
        {(nodeRuns ?? []).map((nodeRun) => {
          const node = nodesById.get(nodeRun.node_id);
          const Icon = NODE_RUN_ICON[nodeRun.status] ?? Loader2;
          const isFailure = nodeRun.status === "error" || nodeRun.status === "cancelled";
          const isSpinning = nodeRun.status === "queued" || nodeRun.status === "running";
          return (
            <li
              key={nodeRun.id}
              className={cn(
                "flex flex-col gap-2 rounded-md px-2 py-1.5 text-sm",
                isFailure ? "bg-destructive-soft text-destructive-strong" : "text-foreground"
              )}
            >
              <div className="flex items-start gap-2">
                <Icon
                  className={cn(
                    "mt-0.5 size-3.5 shrink-0",
                    isFailure && "text-destructive",
                    isSpinning && "animate-spin text-primary"
                  )}
                />
                <span className="min-w-0 flex-1 break-words">{nodeRunSummary(nodeRun, node)}</span>
              </div>
              {nodeRun.status === "paused_for_approval" && (
                <ApprovalControls
                  nodeId={nodeRun.node_id}
                  onResolve={(decision, comment) =>
                    resolveApproval.mutate({ nodeId: nodeRun.node_id, decision, comment })
                  }
                  isPending={resolveApproval.isPending}
                />
              )}
            </li>
          );
        })}
        {(nodeRuns ?? []).length === 0 && (
          <li className="px-2 py-1.5 text-sm text-muted-foreground">Waiting for the run to start…</li>
        )}
      </ol>
    </div>
  );
}

function ApprovalControls({
  nodeId,
  onResolve,
  isPending,
}: {
  nodeId: string;
  onResolve: (decision: "approved" | "rejected", comment: string | null) => void;
  isPending: boolean;
}): React.JSX.Element {
  const [comment, setComment] = React.useState("");

  return (
    <div className="ml-5.5 flex flex-col gap-2 rounded-md border border-warning/30 bg-warning-soft p-2.5">
      <Textarea
        value={comment}
        onChange={(event) => setComment(event.target.value)}
        placeholder="Comment (optional)"
        rows={2}
        className="bg-background text-xs"
        aria-label={`Comment for approval on step ${nodeId}`}
      />
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          disabled={isPending}
          onClick={() => onResolve("approved", comment.trim() || null)}
        >
          Approve
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={isPending}
          onClick={() => onResolve("rejected", comment.trim() || null)}
        >
          Reject
        </Button>
      </div>
    </div>
  );
}
