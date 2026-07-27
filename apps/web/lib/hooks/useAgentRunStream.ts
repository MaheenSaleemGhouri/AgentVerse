import { useEffect, useRef, useState } from "react";

export type RunStepType =
  | "run_started"
  | "retrieval"
  | "llm_call"
  | "tool_call"
  | "run_completed"
  | "run_failed";

export interface RunStepEvent {
  type: RunStepType;
  sequence: number;
  payload: Record<string, unknown>;
  cost_micro_usd: number | null;
}

export type RunStreamStatus = "connecting" | "streaming" | "closed" | "error";

const TERMINAL_STEP_TYPES = new Set<RunStepType>(["run_completed", "run_failed"]);
const FLUSH_INTERVAL_MS = 150;

interface UseAgentRunStreamResult {
  steps: RunStepEvent[];
  status: RunStreamStatus;
  /** Summed directly from persisted `cost_micro_usd` values (Phase 2's
   * cost_accounting primitive, never recomputed here — CLAUDE.md §4
   * Cost Optimization / this phase's DRY risk). */
  totalCostMicroUsd: number;
}

/**
 * Consumes the BFF-proxied SSE run-stream (app/api/runs/[runId]/stream)
 * for `runId`. High-frequency step events are buffered in a ref and
 * flushed into React state on an interval, never per-event `setState`
 * (CLAUDE.md §6 React 19) — the log viewer would otherwise re-render on
 * every token-level step during a busy run.
 */
export function useAgentRunStream(
  workspaceId: string,
  agentId: string,
  runId: string | null
): UseAgentRunStreamResult {
  const [steps, setSteps] = useState<RunStepEvent[]>([]);
  const [status, setStatus] = useState<RunStreamStatus>("connecting");
  const bufferRef = useRef<RunStepEvent[]>([]);

  useEffect(() => {
    if (!runId) {
      return;
    }

    setSteps([]);
    setStatus("connecting");
    bufferRef.current = [];

    const source = new EventSource(
      `/api/runs/${runId}/stream?workspaceId=${encodeURIComponent(workspaceId)}&agentId=${encodeURIComponent(agentId)}`
    );

    const flush = (): void => {
      if (bufferRef.current.length === 0) {
        return;
      }
      const batch = bufferRef.current;
      bufferRef.current = [];
      setSteps((prev) => [...prev, ...batch]);
    };

    const intervalId = window.setInterval(flush, FLUSH_INTERVAL_MS);

    source.onopen = () => setStatus("streaming");

    source.onmessage = (event: MessageEvent<string>) => {
      const step = JSON.parse(event.data) as RunStepEvent;
      bufferRef.current.push(step);
      if (TERMINAL_STEP_TYPES.has(step.type)) {
        flush();
        setStatus("closed");
        source.close();
      }
    };

    source.onerror = () => {
      flush();
      if (source.readyState === EventSource.CLOSED) {
        setStatus((prev) => (prev === "closed" ? prev : "error"));
      }
    };

    return () => {
      window.clearInterval(intervalId);
      source.close();
    };
  }, [workspaceId, agentId, runId]);

  const totalCostMicroUsd = steps.reduce((sum, step) => sum + (step.cost_micro_usd ?? 0), 0);

  return { steps, status, totalCostMicroUsd };
}
