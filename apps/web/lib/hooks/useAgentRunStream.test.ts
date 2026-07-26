import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAgentRunStream, type RunStepEvent } from "./useAgentRunStream";

class FakeEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  static instances: FakeEventSource[] = [];

  readyState = FakeEventSource.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }

  emit(step: RunStepEvent): void {
    this.onmessage?.({ data: JSON.stringify(step) } as MessageEvent<string>);
  }

  close(): void {
    this.readyState = FakeEventSource.CLOSED;
  }
}

function step(overrides: Partial<RunStepEvent>): RunStepEvent {
  return { type: "llm_call", sequence: 1, payload: {}, cost_micro_usd: null, ...overrides };
}

describe("useAgentRunStream", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("buffers rapid events and flushes them as one batch on the interval, not per-event", () => {
    const { result } = renderHook(() => useAgentRunStream("ws-1", "agent-1", "run-1"));
    const source = FakeEventSource.instances[0]!;

    act(() => {
      source.emit(step({ sequence: 1, payload: { text: "a" } }));
      source.emit(step({ sequence: 2, payload: { text: "b" } }));
      source.emit(step({ sequence: 3, payload: { text: "c" } }));
    });

    // Not yet flushed — buffered until the next interval tick.
    expect(result.current.steps).toHaveLength(0);

    act(() => {
      vi.advanceTimersByTime(150);
    });

    expect(result.current.steps).toHaveLength(3);
    expect(result.current.steps.map((s) => s.sequence)).toEqual([1, 2, 3]);
  });

  it("flushes immediately and closes the connection on a terminal step", () => {
    const { result } = renderHook(() => useAgentRunStream("ws-1", "agent-1", "run-1"));
    const source = FakeEventSource.instances[0]!;

    act(() => {
      source.emit(
        step({ type: "run_completed", sequence: 1, payload: { prompt_tokens: 5, completion_tokens: 10 }, cost_micro_usd: 42 })
      );
    });

    expect(result.current.steps).toHaveLength(1);
    expect(result.current.status).toBe("closed");
    expect(source.readyState).toBe(FakeEventSource.CLOSED);
  });

  it("sums cost_micro_usd directly from step events without recomputation", () => {
    const { result } = renderHook(() => useAgentRunStream("ws-1", "agent-1", "run-1"));
    const source = FakeEventSource.instances[0]!;

    act(() => {
      source.emit(step({ sequence: 1, cost_micro_usd: 100 }));
      source.emit(step({ sequence: 2, cost_micro_usd: 200 }));
      vi.advanceTimersByTime(150);
    });

    expect(result.current.totalCostMicroUsd).toBe(300);
  });

  it("does nothing when runId is null", () => {
    const { result } = renderHook(() => useAgentRunStream("ws-1", "agent-1", null));

    expect(FakeEventSource.instances).toHaveLength(0);
    expect(result.current.status).toBe("connecting");
  });

  it("closes the EventSource on unmount", () => {
    const { unmount } = renderHook(() => useAgentRunStream("ws-1", "agent-1", "run-1"));
    const source = FakeEventSource.instances[0]!;

    unmount();

    expect(source.readyState).toBe(FakeEventSource.CLOSED);
  });
});
