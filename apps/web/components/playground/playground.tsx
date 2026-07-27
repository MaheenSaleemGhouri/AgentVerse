"use client";

import { Bot, CornerDownLeft, MessageSquare, Rocket, User } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { runAgentAction } from "@/lib/api/actions";
import type { Agent } from "@/lib/api/agents";
import { useAgentRunStream } from "@/lib/hooks/useAgentRunStream";

import { RuntimeMonitor } from "@/components/playground/runtime-monitor";
import { EmptyState } from "@/components/patterns/empty-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

interface Turn {
  id: string;
  prompt: string;
  runId: string | null;
  /** Assembled from the run's `llm_call` steps once they arrive. */
  answer: string | null;
  failed: boolean;
}

/**
 * The chat surface over Phase 4's run API.
 *
 * The transcript is session-local by design: `POST .../runs` and the SSE
 * stream are the only run endpoints that exist, so there is nothing to
 * rehydrate a past conversation from. That is stated in the UI rather
 * than papered over with fake history.
 */
export function Playground({
  workspaceId,
  agents,
  preselectedAgentId,
}: {
  workspaceId: string;
  agents: Agent[];
  preselectedAgentId: string | null;
}): React.JSX.Element {
  const runnable = React.useMemo(
    () => agents.filter((agent) => agent.status === "active"),
    [agents]
  );

  const [agentId, setAgentId] = React.useState<string>(
    () => preselectedAgentId ?? runnable[0]?.id ?? ""
  );
  const [prompt, setPrompt] = React.useState("");
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [turns, setTurns] = React.useState<Turn[]>([]);

  const activeTurn = turns.at(-1) ?? null;
  const { steps, status, totalCostMicroUsd } = useAgentRunStream(
    workspaceId,
    agentId,
    activeTurn?.runId ?? null
  );

  // Fold the streamed steps back into the transcript so the answer
  // appears in the conversation, not only in the trace panel.
  React.useEffect(() => {
    if (!activeTurn?.runId) return;
    const text = steps
      .filter((step) => step.type === "llm_call")
      .map((step) => (typeof step.payload.text === "string" ? step.payload.text : ""))
      .filter(Boolean)
      .join("\n\n");
    const failed = steps.some((step) => step.type === "run_failed");

    setTurns((current) =>
      current.map((turn) =>
        turn.id === activeTurn.id ? { ...turn, answer: text || null, failed } : turn
      )
    );
  }, [steps, activeTurn?.id, activeTurn?.runId]);

  const selectedAgent = agents.find((agent) => agent.id === agentId) ?? null;
  const isStreaming = status === "connecting" || status === "streaming";
  const canSend = Boolean(agentId) && prompt.trim().length > 0 && !isSubmitting && !isStreaming;

  async function submit(): Promise<void> {
    if (!canSend) return;
    const turnId = crypto.randomUUID();
    const sent = prompt.trim();
    setTurns((current) => [
      ...current,
      { id: turnId, prompt: sent, runId: null, answer: null, failed: false },
    ]);
    setPrompt("");
    setIsSubmitting(true);
    try {
      // The idempotency key is per submission, so a double-click or a
      // retried request cannot trigger (or bill for) two runs.
      const run = await runAgentAction(workspaceId, agentId, sent, crypto.randomUUID());
      setTurns((current) =>
        current.map((turn) => (turn.id === turnId ? { ...turn, runId: run.id } : turn))
      );
    } catch {
      toast.error("Could not start the run — check the agent is still published.");
      setTurns((current) =>
        current.map((turn) => (turn.id === turnId ? { ...turn, failed: true } : turn))
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  if (agents.length === 0) {
    return (
      <EmptyState
        icon={Bot}
        title="No agents to run"
        description="Build an agent first, then publish it to make it runnable here."
        action={
          <Button asChild>
            <Link href={`/dashboard/${workspaceId}/agents`}>Go to agents</Link>
          </Button>
        }
      />
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_400px]">
      <div className="flex min-w-0 flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <Select value={agentId} onValueChange={setAgentId}>
            <SelectTrigger className="w-72">
              <SelectValue placeholder="Choose an agent" />
            </SelectTrigger>
            <SelectContent>
              {agents.map((agent) => (
                <SelectItem key={agent.id} value={agent.id} disabled={agent.status !== "active"}>
                  {agent.name}
                  {agent.status !== "active" && " — not published"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {turns.length > 0 && (
            <Button variant="ghost" size="sm" onClick={() => setTurns([])}>
              Clear conversation
            </Button>
          )}
        </div>

        {selectedAgent && selectedAgent.status !== "active" && (
          <Alert tone="warning">
            <Rocket />
            <AlertTitle>“{selectedAgent.name}” is not published</AlertTitle>
            <AlertDescription>
              Only published agents can run. Publish it from its detail page, then come back.{" "}
              <Link
                href={`/dashboard/${workspaceId}/agents/${selectedAgent.id}`}
                className="text-primary underline underline-offset-4"
              >
                Open agent
              </Link>
            </AlertDescription>
          </Alert>
        )}

        <Card className="flex min-h-96 flex-col gap-4 p-5">
          {turns.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center">
              <span className="flex size-12 items-center justify-center rounded-full bg-accent text-accent-foreground">
                <MessageSquare className="size-6" aria-hidden="true" />
              </span>
              <p className="font-medium">Send your first message</p>
              <p className="max-w-sm text-sm text-muted-foreground">
                Every step — retrieval, tool calls, model output — streams into the runtime monitor
                as it happens.
              </p>
            </div>
          ) : (
            <div className="flex flex-1 flex-col gap-5">
              {turns.map((turn) => (
                <div key={turn.id} className="space-y-4">
                  <Message role="user" text={turn.prompt} />
                  <Message
                    role="agent"
                    text={turn.answer}
                    isPending={turn.runId !== null && turn.answer === null && !turn.failed}
                    failed={turn.failed}
                  />
                </div>
              ))}
            </div>
          )}

          <div className="mt-auto space-y-2">
            <Textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              onKeyDown={(event) => {
                // Enter sends, Shift+Enter newlines — the convention every
                // chat surface the user already knows uses.
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void submit();
                }
              }}
              placeholder="Ask your agent something…"
              aria-label="Message"
              rows={3}
              maxLength={8000}
              disabled={!agentId}
            />
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                Enter to send · Shift+Enter for a new line
              </span>
              <Button onClick={() => void submit()} disabled={!canSend}>
                <CornerDownLeft />
                {isSubmitting ? "Starting…" : isStreaming ? "Running…" : "Send"}
              </Button>
            </div>
          </div>
        </Card>
      </div>

      <RuntimeMonitor
        steps={steps}
        status={activeTurn?.runId ? status : "idle"}
        totalCostMicroUsd={totalCostMicroUsd}
        runId={activeTurn?.runId ?? null}
      />
    </div>
  );
}

function Message({
  role,
  text,
  isPending,
  failed,
}: {
  role: "user" | "agent";
  text: string | null;
  isPending?: boolean;
  failed?: boolean;
}): React.JSX.Element {
  const Icon = role === "user" ? User : Bot;
  return (
    <div className="flex gap-3">
      <span
        aria-hidden="true"
        className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground"
      >
        <Icon className="size-3.5" />
      </span>
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-xs font-medium text-muted-foreground">
          {role === "user" ? "You" : "Agent"}
        </p>
        {failed ? (
          <p className="text-sm text-destructive">The run failed — see the runtime monitor.</p>
        ) : isPending ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <span className="size-1.5 animate-pulse rounded-full bg-primary" aria-hidden="true" />
            Thinking…
          </p>
        ) : (
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{text ?? "—"}</p>
        )}
      </div>
    </div>
  );
}
