import { useEffect, useRef, useState } from "react";

/**
 * The multi-agent runtime event vocabulary.
 *
 * `execution_events.event_type` is deliberately free-form text on the
 * backend — the set grows per topology, and adding one must never
 * require a migration. This union is therefore the enforcement point:
 * the renderer is exhaustive over it, so a new backend event type fails
 * the build here rather than rendering as a blank row.
 *
 * `unknown_event` is the deliberate escape hatch for the one case that
 * cannot be a build error — an older frontend deployed against a newer
 * API mid-rollout. It renders as a labelled raw payload, not as nothing.
 */
export type TeamEventType =
  | "session_started"
  | "agent_started"
  | "agent_completed"
  | "agent_failed"
  | "handoff"
  | "handoff_unresolved"
  | "session_completed"
  | "session_failed"
  | "unknown_event";

const KNOWN_EVENT_TYPES = new Set<TeamEventType>([
  "session_started",
  "agent_started",
  "agent_completed",
  "agent_failed",
  "handoff",
  "handoff_unresolved",
  "session_completed",
  "session_failed",
  "unknown_event",
]);

export interface TeamEvent {
  type: TeamEventType;
  sequence: number;
  agent_id: string | null;
  payload: Record<string, unknown>;
  cost_micro_usd: number | null;
}

export type TeamStreamStatus = "connecting" | "streaming" | "closed" | "error";

const TERMINAL_EVENT_TYPES = new Set<TeamEventType>(["session_completed", "session_failed"]);
const FLUSH_INTERVAL_MS = 150;

export interface UseTeamSessionStreamResult {
  events: TeamEvent[];
  status: TeamStreamStatus;
  /** Summed from persisted `cost_micro_usd`, never recomputed here. */
  totalCostMicroUsd: number;
  /** Agents that started and have not yet completed or failed. */
  activeAgentIds: string[];
  handoffCount: number;
}

/**
 * Narrows a wire event — whose `type` is `string`, because the backend
 * keeps `execution_events.event_type` free-form so a new event type
 * never needs a migration — into the renderable union.
 *
 * Exported because the same normalisation is needed for events read back
 * from the durable `/events` endpoint, not just for the live stream: a
 * finished session must render identically to a live one, and two
 * separate narrowings would be two chances to disagree.
 */
export function toTeamEvent(raw: {
  type: string;
  sequence: number;
  agent_id: string | null;
  payload: Record<string, unknown>;
  cost_micro_usd: number | null;
}): TeamEvent {
  return KNOWN_EVENT_TYPES.has(raw.type as TeamEventType)
    ? { ...raw, type: raw.type as TeamEventType }
    : { ...raw, type: "unknown_event", payload: { original_type: raw.type, ...raw.payload } };
}

/**
 * Consumes the BFF-proxied team-session SSE stream.
 *
 * Events are buffered in a ref and flushed on an interval rather than
 * `setState` per event (CLAUDE.md §6): a parallel topology emits from
 * several members at once, and a re-render per event would make the
 * timeline stutter exactly when it is busiest.
 */
export function useTeamSessionStream(
  workspaceId: string,
  teamId: string,
  sessionId: string | null,
  { enabled = true }: { enabled?: boolean } = {}
): UseTeamSessionStreamResult {
  const [events, setEvents] = useState<TeamEvent[]>([]);
  const [status, setStatus] = useState<TeamStreamStatus>("connecting");
  const bufferRef = useRef<TeamEvent[]>([]);

  useEffect(() => {
    if (!sessionId || !enabled) return;

    setEvents([]);
    setStatus("connecting");
    bufferRef.current = [];

    const source = new EventSource(
      `/api/team-sessions/${sessionId}/stream?workspaceId=${encodeURIComponent(workspaceId)}&teamId=${encodeURIComponent(teamId)}`
    );

    const flush = (): void => {
      if (bufferRef.current.length === 0) return;
      const batch = bufferRef.current;
      bufferRef.current = [];
      setEvents((prev) => [...prev, ...batch]);
    };

    const intervalId = window.setInterval(flush, FLUSH_INTERVAL_MS);

    source.onopen = () => setStatus("streaming");

    source.onmessage = (message: MessageEvent<string>) => {
      const event = toTeamEvent(JSON.parse(message.data));
      bufferRef.current.push(event);
      if (TERMINAL_EVENT_TYPES.has(event.type)) {
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

    // Always closed on unmount — a leaked SSE connection when navigating
    // away from a runtime view is a defect, not an edge case.
    return () => {
      window.clearInterval(intervalId);
      source.close();
    };
  }, [workspaceId, teamId, sessionId, enabled]);

  const totalCostMicroUsd = events.reduce((sum, event) => sum + (event.cost_micro_usd ?? 0), 0);

  // Derived rather than stored: a separate "running agents" state would
  // be a second source of truth that can disagree with the event log.
  const active = new Set<string>();
  for (const event of events) {
    if (!event.agent_id) continue;
    if (event.type === "agent_started") active.add(event.agent_id);
    if (event.type === "agent_completed" || event.type === "agent_failed") {
      active.delete(event.agent_id);
    }
  }

  return {
    events,
    status,
    totalCostMicroUsd,
    activeAgentIds: [...active],
    handoffCount: events.filter((event) => event.type === "handoff").length,
  };
}
