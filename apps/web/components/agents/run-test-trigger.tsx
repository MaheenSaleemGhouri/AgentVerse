"use client";

import { Play } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { runAgentAction } from "@/lib/api/actions";

import { RunTraceViewer } from "@/components/agents/run-trace-viewer";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export function RunTestTrigger({
  workspaceId,
  agentId,
  canRun,
}: {
  workspaceId: string;
  agentId: string;
  canRun: boolean;
}): React.JSX.Element {
  const [prompt, setPrompt] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);

  async function handleRun(): Promise<void> {
    setIsSubmitting(true);
    try {
      const run = await runAgentAction(workspaceId, agentId, prompt, crypto.randomUUID());
      setActiveRunId(run.id);
    } catch {
      toast.error("Could not submit the run — try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div>
        <p className="font-medium">Test run</p>
        <p className="text-sm text-muted-foreground">
          {canRun ? "Send a message to your published agent." : "Publish this agent to test it."}
        </p>
      </div>
      <Textarea
        placeholder="Ask your agent something…"
        rows={3}
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        disabled={!canRun}
      />
      <Button onClick={() => void handleRun()} disabled={!canRun || isSubmitting}>
        <Play />
        {isSubmitting ? "Submitting…" : "Run"}
      </Button>
      {activeRunId && (
        <RunTraceViewer workspaceId={workspaceId} agentId={agentId} runId={activeRunId} />
      )}
    </div>
  );
}
