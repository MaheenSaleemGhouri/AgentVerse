"use client";

import { Play } from "lucide-react";
import * as React from "react";

import type { WorkflowNode } from "@/lib/api/workflows";
import { useSubmitWorkflowRun } from "@/lib/queries/workflows";

import { WorkflowRunStatus } from "@/components/workflows/workflow-run-status";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export function RunWorkflowTrigger({
  workspaceId,
  workflowId,
  canRun,
  nodes,
}: {
  workspaceId: string;
  workflowId: string;
  canRun: boolean;
  nodes: WorkflowNode[];
}): React.JSX.Element {
  const [prompt, setPrompt] = React.useState("");
  const [activeRunId, setActiveRunId] = React.useState<string | null>(null);
  const submitRun = useSubmitWorkflowRun(workspaceId, workflowId);

  const nodesById = React.useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  async function handleRun(): Promise<void> {
    const run = await submitRun.mutateAsync({ prompt });
    setActiveRunId(run.id);
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div>
        <p className="font-medium">Test run</p>
        <p className="text-sm text-muted-foreground">
          {canRun
            ? "Trigger the published version and watch each node run."
            : "Publish this workflow to run it."}
        </p>
      </div>
      <Textarea
        placeholder="Trigger input — reaches the first step as {{trigger.input}}…"
        rows={3}
        value={prompt}
        onChange={(event) => setPrompt(event.target.value)}
        disabled={!canRun}
      />
      <Button onClick={() => void handleRun()} disabled={!canRun || submitRun.isPending}>
        <Play />
        {submitRun.isPending ? "Submitting…" : "Run"}
      </Button>
      {activeRunId && (
        <WorkflowRunStatus
          workspaceId={workspaceId}
          workflowId={workflowId}
          runId={activeRunId}
          nodesById={nodesById}
          showFullRunLink
        />
      )}
    </div>
  );
}
