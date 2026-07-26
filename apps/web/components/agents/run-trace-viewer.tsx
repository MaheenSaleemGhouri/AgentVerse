"use client";

import { CheckCircle2, Loader2, MessageSquare, Wrench, XCircle } from "lucide-react";

import { useAgentRunStream, type RunStepEvent } from "@/lib/hooks/useAgentRunStream";
import { cn } from "@/lib/utils";

function formatMicroUsd(microUsd: number): string {
  return `$${(microUsd / 1_000_000).toFixed(4)}`;
}

function stepSummary(step: RunStepEvent): string {
  switch (step.type) {
    case "run_started":
      return "Run started";
    case "llm_call":
      return typeof step.payload.text === "string" ? step.payload.text : "Model responded";
    case "tool_call":
      if (step.payload.phase === "called") {
        return `Called tool "${String(step.payload.name)}"`;
      }
      return `Tool returned: ${String(step.payload.output)}`;
    case "run_completed":
      return `Run completed (${String(step.payload.prompt_tokens)} prompt + ${String(step.payload.completion_tokens)} completion tokens)`;
    case "run_failed":
      return `Run failed: ${String(step.payload.reason)}`;
    default:
      return "Step";
  }
}

const STEP_ICON: Record<RunStepEvent["type"], React.ComponentType<{ className?: string }>> = {
  run_started: Loader2,
  llm_call: MessageSquare,
  tool_call: Wrench,
  run_completed: CheckCircle2,
  run_failed: XCircle,
};

export function RunTraceViewer({
  workspaceId,
  agentId,
  runId,
}: {
  workspaceId: string;
  agentId: string;
  runId: string;
}): React.JSX.Element {
  const { steps, status, totalCostMicroUsd } = useAgentRunStream(workspaceId, agentId, runId);
  const lastStep = steps.at(-1);

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium">
          {status === "streaming" || status === "connecting" ? (
            <Loader2 className="size-4 animate-spin text-primary" />
          ) : status === "error" ? (
            <XCircle className="size-4 text-destructive" />
          ) : (
            <CheckCircle2 className="size-4 text-success" />
          )}
          Run {runId.slice(0, 8)}
        </div>
        <span className="font-mono text-sm tabular-nums text-muted-foreground">
          {formatMicroUsd(totalCostMicroUsd)}
        </span>
      </div>

      {/* Announces only the latest step, not the whole growing list —
          over-announcing every token would drown a screen-reader user
          (CLAUDE.md §15). */}
      <p aria-live="polite" className="sr-only">
        {lastStep ? stepSummary(lastStep) : "Waiting for run to start"}
      </p>

      <ol className="flex max-h-80 flex-col gap-1.5 overflow-y-auto">
        {steps.map((step) => {
          const Icon = STEP_ICON[step.type];
          const isFailure = step.type === "run_failed";
          return (
            <li
              key={step.sequence}
              className={cn(
                "flex items-start gap-2 rounded-md px-2 py-1.5 text-sm",
                isFailure ? "bg-destructive-soft text-destructive" : "text-foreground"
              )}
            >
              <Icon className={cn("mt-0.5 size-3.5 shrink-0", isFailure && "text-destructive")} />
              <span className="min-w-0 flex-1 break-words">{stepSummary(step)}</span>
              {step.cost_micro_usd !== null && (
                <span className="shrink-0 font-mono text-xs tabular-nums text-muted-foreground">
                  {formatMicroUsd(step.cost_micro_usd)}
                </span>
              )}
            </li>
          );
        })}
        {steps.length === 0 && (
          <li className="px-2 py-1.5 text-sm text-muted-foreground">Connecting to run…</li>
        )}
      </ol>
    </div>
  );
}
