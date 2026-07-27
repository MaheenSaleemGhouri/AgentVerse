import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { toTeamEvent, useTeamSessionStream, type TeamEvent } from "./useTeamSessionStream";

/**
 * What actually arrives on the wire: `type` is a plain string, because
 * the backend keeps `event_type` free-form. Typing the fixture as
 * `Partial<TeamEvent>` would narrow `type` back to the union and make
 * the unknown-event cases unexpressible — which is the one behaviour
 * most worth testing.
 */
type WireEvent = Omit<TeamEvent, "type"> & { type: string };

class FakeEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  static instances: FakeEventSource[] = [];

  readyState = FakeEventSource.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }

  emit(event: WireEvent): void {
    this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent<string>);
  }

  close(): void {
    this.readyState = FakeEventSource.CLOSED;
    this.closed = true;
  }
}

function event(overrides: Partial<WireEvent> & { type: string }): WireEvent {
  return { sequence: 1, agent_id: null, payload: {}, cost_micro_usd: null, ...overrides };
}

describe("toTeamEvent", () => {
  it("passes a known event type through unchanged", () => {
    const result = toTeamEvent({
      type: "handoff",
      sequence: 3,
      agent_id: "a-1",
      payload: { to_agent_id: "a-2" },
      cost_micro_usd: null,
    });
    expect(result.type).toBe("handoff");
    expect(result.payload.to_agent_id).toBe("a-2");
  });

  it("maps an unrecognised type to unknown_event and keeps the original name", () => {
    // The backend keeps `event_type` free-form so a new type never needs
    // a migration. An older frontend must label what it cannot render,
    // never drop it silently.
    const result = toTeamEvent({
      type: "consensus_reached",
      sequence: 1,
      agent_id: null,
      payload: { detail: "x" },
      cost_micro_usd: null,
    });
    expect(result.type).toBe("unknown_event");
    expect(result.payload.original_type).toBe("consensus_reached");
    expect(result.payload.detail).toBe("x");
  });
});

describe("useTeamSessionStream", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("does not open a connection without a session id", () => {
    renderHook(() => useTeamSessionStream("ws-1", "team-1", null));
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it("does not open a connection when disabled", () => {
    // A finished session reads its events from the durable endpoint; a
    // stream that will never receive anything must not be opened.
    renderHook(() => useTeamSessionStream("ws-1", "team-1", "s-1", { enabled: false }));
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it("buffers rapid events and flushes them as one batch, not per event", () => {
    // A parallel topology emits from several members at once; a
    // re-render per event would make the timeline stutter exactly when
    // it is busiest.
    const { result } = renderHook(() => useTeamSessionStream("ws-1", "team-1", "s-1"));
    const source = FakeEventSource.instances[0]!;

    act(() => {
      source.emit(event({ type: "agent_started", sequence: 1, agent_id: "a-1" }));
      source.emit(event({ type: "agent_started", sequence: 2, agent_id: "a-2" }));
    });
    expect(result.current.events).toHaveLength(0);

    act(() => void vi.advanceTimersByTime(200));
    expect(result.current.events).toHaveLength(2);
  });

  it("tracks which agents are still working", () => {
    const { result } = renderHook(() => useTeamSessionStream("ws-1", "team-1", "s-1"));
    const source = FakeEventSource.instances[0]!;

    act(() => {
      source.emit(event({ type: "agent_started", sequence: 1, agent_id: "a-1" }));
      source.emit(event({ type: "agent_started", sequence: 2, agent_id: "a-2" }));
      source.emit(event({ type: "agent_completed", sequence: 3, agent_id: "a-1" }));
      vi.advanceTimersByTime(200);
    });

    expect(result.current.activeAgentIds).toEqual(["a-2"]);
  });

  it("treats a failed agent as no longer running", () => {
    const { result } = renderHook(() => useTeamSessionStream("ws-1", "team-1", "s-1"));
    const source = FakeEventSource.instances[0]!;

    act(() => {
      source.emit(event({ type: "agent_started", sequence: 1, agent_id: "a-1" }));
      source.emit(event({ type: "agent_failed", sequence: 2, agent_id: "a-1" }));
      vi.advanceTimersByTime(200);
    });

    expect(result.current.activeAgentIds).toEqual([]);
  });

  it("sums cost from the events rather than recomputing it", () => {
    const { result } = renderHook(() => useTeamSessionStream("ws-1", "team-1", "s-1"));
    const source = FakeEventSource.instances[0]!;

    act(() => {
      source.emit(event({ type: "agent_completed", sequence: 1, cost_micro_usd: 1200 }));
      source.emit(event({ type: "agent_completed", sequence: 2, cost_micro_usd: 800 }));
      vi.advanceTimersByTime(200);
    });

    expect(result.current.totalCostMicroUsd).toBe(2000);
  });

  it("counts handoffs", () => {
    const { result } = renderHook(() => useTeamSessionStream("ws-1", "team-1", "s-1"));
    const source = FakeEventSource.instances[0]!;

    act(() => {
      source.emit(event({ type: "handoff", sequence: 1 }));
      source.emit(event({ type: "handoff", sequence: 2 }));
      source.emit(event({ type: "agent_started", sequence: 3 }));
      vi.advanceTimersByTime(200);
    });

    expect(result.current.handoffCount).toBe(2);
  });

  it("closes the connection on a terminal event", () => {
    const { result } = renderHook(() => useTeamSessionStream("ws-1", "team-1", "s-1"));
    const source = FakeEventSource.instances[0]!;

    act(() => {
      source.emit(event({ type: "session_completed", sequence: 9 }));
    });

    expect(source.closed).toBe(true);
    expect(result.current.status).toBe("closed");
    // Flushed immediately on terminal, not left waiting for the tick.
    expect(result.current.events).toHaveLength(1);
  });

  it("closes the connection on unmount", () => {
    // A leaked SSE connection when navigating away from a runtime view
    // is a defect, not an edge case.
    const { unmount } = renderHook(() => useTeamSessionStream("ws-1", "team-1", "s-1"));
    const source = FakeEventSource.instances[0]!;
    unmount();
    expect(source.closed).toBe(true);
  });

  it("reports an unrecognised event rather than dropping it", () => {
    const { result } = renderHook(() => useTeamSessionStream("ws-1", "team-1", "s-1"));
    const source = FakeEventSource.instances[0]!;

    act(() => {
      source.emit(event({ type: "something_new_from_the_backend", sequence: 1 }));
      vi.advanceTimersByTime(200);
    });

    expect(result.current.events[0]?.type).toBe("unknown_event");
  });
});
