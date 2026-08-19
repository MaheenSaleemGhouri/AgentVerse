import { useEffect, useRef, useState } from "react";

import { mintCollabTicketAction } from "@/lib/api/actions";

export type CollabEvent =
  | { type: "presence"; user_id: string; name: string }
  | { type: "node_moved"; user_id: string; node_id: string; x: number; y: number }
  | { type: "node_added"; user_id: string; node_id: string; node_type: string; x: number; y: number }
  | { type: "node_removed"; user_id: string; node_id: string }
  | { type: "edge_added"; user_id: string; edge_id: string; from_node_id: string; to_node_id: string }
  | { type: "edge_removed"; user_id: string; edge_id: string };

export type CollabStatus = "connecting" | "open" | "closed" | "error";

// Plain `Omit` does not distribute over a union — `keyof CollabEvent`
// collapses to the fields every variant shares, silently erasing
// `node_id`/`edge_id`/etc. This conditional form forces the
// distribution (a standard TS idiom, not a `CollabEvent`-specific
// workaround), so each variant keeps its own fields minus `user_id`.
type DistributiveOmit<T, K extends keyof T> = T extends unknown ? Omit<T, K> : never;
export type CollabEventInput = DistributiveOmit<CollabEvent, "user_id">;

interface UseWorkflowCollabResult {
  status: CollabStatus;
  /** Every collaborator seen on this channel, keyed by user id — includes self. */
  presence: Map<string, { name: string; lastSeenAt: number }>;
  /** The last non-presence event received, for the canvas to apply. */
  lastEvent: CollabEvent | null;
  send: (event: CollabEventInput) => void;
}

const PRESENCE_INTERVAL_MS = 10_000;
const PRESENCE_STALE_MS = 30_000;

/**
 * Real-time canvas collaboration over the WS relay minted by
 * `POST .../workflows/{id}/collab-ticket` (docs/adr/0016). Unlike
 * `useAgentRunStream`'s same-origin SSE proxy, this connects the browser
 * directly to apps/api's public WS origin — a long-lived bidirectional
 * socket cannot go through the cookie-resolving proxy trick SSE uses,
 * since the browser never holds the Bearer token to attach to a raw
 * `EventSource`-style request, and a WebSocket cannot set custom headers
 * either. The ticket (single-use, ~30s TTL) is the auth instead.
 */
export function useWorkflowCollab(
  workspaceId: string,
  workflowId: string,
  displayName: string
): UseWorkflowCollabResult {
  const [status, setStatus] = useState<CollabStatus>("connecting");
  const [presence, setPresence] = useState<Map<string, { name: string; lastSeenAt: number }>>(
    new Map()
  );
  const [lastEvent, setLastEvent] = useState<CollabEvent | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const selfIdRef = useRef<string | null>(null);

  useEffect(() => {
    const wsBase = process.env.NEXT_PUBLIC_API_WS_URL;
    if (!wsBase) {
      // No public WS origin configured — the canvas still works, it
      // just never connects (graceful degradation, not a hard error).
      setStatus("closed");
      return;
    }

    let cancelled = false;
    let socket: WebSocket | null = null;
    let presenceIntervalId: number | undefined;

    async function connect(): Promise<void> {
      setStatus("connecting");
      const { ticket } = await mintCollabTicketAction(workspaceId, workflowId);
      if (cancelled) return;

      socket = new WebSocket(
        `${wsBase}/api/v1/workspaces/${workspaceId}/workflows/${workflowId}/collab?ticket=${encodeURIComponent(ticket)}`
      );
      socketRef.current = socket;

      socket.onopen = () => {
        if (cancelled) return;
        setStatus("open");
        socket?.send(JSON.stringify({ type: "presence", name: displayName }));
        presenceIntervalId = window.setInterval(() => {
          socket?.send(JSON.stringify({ type: "presence", name: displayName }));
        }, PRESENCE_INTERVAL_MS);
      };

      socket.onmessage = (message: MessageEvent<string>) => {
        let event: CollabEvent;
        try {
          event = JSON.parse(message.data) as CollabEvent;
        } catch {
          return;
        }
        if (selfIdRef.current === null && event.type === "presence" && event.name === displayName) {
          selfIdRef.current = event.user_id;
        }
        if (event.type === "presence") {
          setPresence((prev) => {
            const next = new Map(prev);
            next.set(event.user_id, { name: event.name, lastSeenAt: Date.now() });
            return next;
          });
          return;
        }
        setLastEvent(event);
      };

      socket.onerror = () => {
        if (!cancelled) setStatus("error");
      };

      socket.onclose = () => {
        if (!cancelled) setStatus("closed");
      };
    }

    void connect();

    // Collaborators who stopped sending presence pings age out of the
    // roster rather than lingering forever after a tab close the socket
    // never cleanly reported.
    const pruneIntervalId = window.setInterval(() => {
      setPresence((prev) => {
        const cutoff = Date.now() - PRESENCE_STALE_MS;
        const next = new Map([...prev].filter(([, v]) => v.lastSeenAt >= cutoff));
        return next.size === prev.size ? prev : next;
      });
    }, PRESENCE_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(presenceIntervalId);
      window.clearInterval(pruneIntervalId);
      // A leaked socket when navigating away from the builder is a
      // defect, not an edge case (CLAUDE.md §6, mirroring
      // useAgentRunStream's SSE cleanup).
      socket?.close();
      socketRef.current = null;
    };
  }, [workspaceId, workflowId, displayName]);

  function send(event: CollabEventInput): void {
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(event));
    }
  }

  return { status, presence, lastEvent, send };
}
