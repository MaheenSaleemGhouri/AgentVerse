"use client";

import {
  BookOpen,
  CheckCircle2,
  CircleDashed,
  Loader2,
  MessageSquare,
  Play,
  Wrench,
  XCircle,
} from "lucide-react";
import * as React from "react";

import type { RunStepEvent, RunStepType, RunStreamStatus } from "@/lib/hooks/useAgentRunStream";
import { formatMicroUsd } from "@/lib/format";
import { cn } from "@/lib/utils";

import { CopyButton } from "@/components/patterns/copy-button";
import { StatusBadge } from "@/components/patterns/status-badge";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

/**
 * The execution timeline for the run currently streaming.
 *
 * Exhaustive over `RunStepType` (`never`-checked) so a step type added
 * to the backend fails this build until it is handled here, rather than
 * silently rendering as a blank row (CLAUDE.md §6).
 */
const STEP_ICON: Record<RunStepType, React.ComponentType<{ className?: string }>> = {
  run_started: Play,
  retrieval: BookOpen,
  llm_call: MessageSquare,
  tool_call: Wrench,
  run_completed: CheckCircle2,
  run_failed: XCircle,
};

function summarize(step: RunStepEvent): string {
  switch (step.type) {
    case "run_started":
      return "Run started";
    case "retrieval":
      return retrievalSummary(step);
    case "llm_call":
      return typeof step.payload.text === "string" ? step.payload.text : "Model responded";
    case "tool_call":
      return step.payload.phase === "called"
        ? `Called ${String(step.payload.name)}`
        : `Returned: ${String(step.payload.output)}`;
    case "run_completed":
      return `Completed — ${String(step.payload.prompt_tokens)} prompt + ${String(step.payload.completion_tokens)} completion tokens`;
    case "run_failed":
      return `Failed: ${String(step.payload.reason)}`;
    default: {
      const exhaustive: never = step.type;
      return exhaustive;
    }
  }
}

function retrievalSummary(step: RunStepEvent): string {
  if (typeof step.payload.error === "string") {
    return `Retrieval unavailable — answering ungrounded (${step.payload.error})`;
  }
  const citations = Array.isArray(step.payload.citations) ? step.payload.citations.length : 0;
  if (citations === 0) return "No matching documents — answering ungrounded";
  const skipped = Array.isArray(step.payload.skipped_knowledge_base_ids)
    ? step.payload.skipped_knowledge_base_ids.length
    : 0;
  return `Retrieved ${citations} chunk${citations === 1 ? "" : "s"}${
    skipped > 0 ? ` · ${skipped} KB skipped` : ""
  }`;
}

export function RuntimeMonitor({
  steps,
  status,
  totalCostMicroUsd,
  runId,
}: {
  steps: RunStepEvent[];
  status: RunStreamStatus | "idle";
  totalCostMicroUsd: number;
  runId: string | null;
}): React.JSX.Element {
  const scrollRef = React.useRef<HTMLDivElement>(null);

  // Follow the tail as steps arrive. Only while the run is live, so a
  // user reading back through a finished trace isn't yanked to the end.
  React.useEffect(() => {
    if (status !== "streaming") return;
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [steps.length, status]);

  const lastStep = steps.at(-1);

  return (
    <Card className="flex h-fit max-h-[calc(100vh-10rem)] flex-col gap-0 p-0 xl:sticky xl:top-20">
      <div className="flex items-center justify-between gap-2 border-b border-border px-5 py-4">
        <div className="min-w-0">
          <h2 className="text-sm font-medium">Runtime monitor</h2>
          {runId ? (
            <div className="flex items-center gap-1">
              <code className="truncate font-mono text-xs text-muted-foreground">
                {runId.slice(0, 8)}
              </code>
              <CopyButton value={runId} label="Copy run ID" size="icon-xs" />
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">No active run</p>
          )}
        </div>
        <MonitorStatus status={status} />
      </div>

      {/* Announces only the newest step — narrating every step of a busy
          run would drown a screen-reader user (CLAUDE.md §15). */}
      <p aria-live="polite" className="sr-only">
        {lastStep ? summarize(lastStep) : "Waiting for a run"}
      </p>

      {steps.length === 0 ? (
        <div className="flex flex-col items-center gap-2 px-5 py-16 text-center">
          <CircleDashed className="size-6 text-muted-foreground" aria-hidden="true" />
          <p className="text-sm text-muted-foreground">
            Steps appear here the moment a run starts.
          </p>
        </div>
      ) : (
        <ScrollArea className="flex-1" viewportRef={scrollRef}>
          <ol className="space-y-0 px-5 py-3">
            {steps.map((step, index) => {
              const Icon = STEP_ICON[step.type];
              const isFailure = step.type === "run_failed";
              const isLast = index === steps.length - 1;
              return (
                <li key={step.sequence} className="relative flex gap-3 pb-4">
                  {/* Timeline rail — connects steps into one run rather
                      than reading as a flat list of unrelated rows. */}
                  {!isLast && (
                    <span
                      aria-hidden="true"
                      className="absolute top-7 bottom-0 left-[11px] w-px bg-border"
                    />
                  )}
                  <span
                    aria-hidden="true"
                    className={cn(
                      "relative z-10 flex size-6 shrink-0 items-center justify-center rounded-full border",
                      isFailure
                        ? "border-destructive/30 bg-destructive-soft text-destructive"
                        : step.type === "run_completed"
                          ? "border-success/30 bg-success-soft text-success"
                          : "border-border bg-card text-muted-foreground"
                    )}
                  >
                    <Icon className="size-3" />
                  </span>
                  <div className="min-w-0 flex-1 pt-0.5">
                    <p
                      className={cn(
                        "text-sm break-words",
                        isFailure ? "text-destructive" : "text-foreground"
                      )}
                    >
                      {summarize(step)}
                    </p>
                    {step.cost_micro_usd !== null && (
                      <p className="mt-0.5 font-mono text-xs text-muted-foreground tabular-nums">
                        {formatMicroUsd(step.cost_micro_usd)}
                      </p>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </ScrollArea>
      )}

      <Separator />
      <div className="flex items-center justify-between px-5 py-3">
        <span className="text-xs text-muted-foreground">Run cost</span>
        <span className="font-mono text-sm font-medium tabular-nums">
          {formatMicroUsd(totalCostMicroUsd)}
        </span>
      </div>
    </Card>
  );
}

function MonitorStatus({ status }: { status: RunStreamStatus | "idle" }): React.JSX.Element {
  switch (status) {
    case "connecting":
      return (
        <StatusBadge tone="info" pulse>
          Connecting
        </StatusBadge>
      );
    case "streaming":
      return (
        <StatusBadge tone="info" pulse>
          <Loader2 className="size-3 animate-spin" aria-hidden="true" />
          Running
        </StatusBadge>
      );
    case "closed":
      return <StatusBadge tone="success">Finished</StatusBadge>;
    case "error":
      return <StatusBadge tone="danger">Stream lost</StatusBadge>;
    case "idle":
      return <StatusBadge tone="neutral">Idle</StatusBadge>;
    default: {
      const exhaustive: never = status;
      return exhaustive;
    }
  }
}
