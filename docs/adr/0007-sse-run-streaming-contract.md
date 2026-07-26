# ADR 0007: SSE Run-Streaming Contract

## Numbering note

`docs/roadmap.md`'s Phase 4 deliverables list suggests this ADR as `0006-sse-run-streaming-contract.md`. That number was already consumed by Phase 2's `0006-provider-abstraction-and-openai-integration.md` (itself a bump from the roadmap's suggested `0005`, already taken by Phase 1). Per ADR immutability discipline (CLAUDE.md §13: an accepted ADR is never renumbered or silently edited), this is `0007`, continuing the same documented-deviation pattern.

## Context

Phase 4 ships the platform's first live-streaming, user-facing feature: a workspace member runs an agent and watches its execution trace stream in real time. `decision-log.md` #19 ("Why SSE") already committed to Server-Sent Events over Redis pub/sub as the transport, specifically citing:

- One-directional server→client fits the execution-trace use case exactly.
- SSE's simplicity relative to WebSockets for this direction.
- "Supports `Last-Event-ID`-style resume so a client reconnecting mid-run doesn't lose history."
- "The full trace must be durably stored (Postgres/object storage), not held only in memory, so resume works."

Phase 3 reserved the `run:{run_id}:events` pub/sub channel name as scaffolding only (`docs/systems/redis-channels.md`), explicitly deferring the event schema to "Phase 4, where a real consumer exists." This ADR is that decision.

## Decision

**Event envelope.** Every SSE frame is `data: {json}\n\n` with this shape:

```json
{"type": "llm_call", "sequence": 4, "payload": {"text": "..."}, "cost_micro_usd": 12}
```

- `type` is exactly the `agent_run_steps.step_type` vocabulary (`run_started`, `llm_call`, `tool_call`, `run_completed`, `run_failed`) — the same enum used in the database column, not a second parallel vocabulary. A live-streamed event and a backfilled-from-Postgres event are byte-shape-identical; a client never needs to special-case "this came from history" vs. "this came in live."
- `sequence` matches `agent_run_steps.sequence` — the field a client uses for ordering/dedup if events arrive out of order across a reconnect boundary.
- `payload` is step-type-specific (e.g. `{"text": ...}` for `llm_call`, `{"phase": "called"|"output", "name": ..., "arguments"|"output": ...}` for `tool_call`).
- `cost_micro_usd` is `null` except on `run_completed`, where it carries the final total from `cost_accounting.calculate_cost_micro_usd` — displayed, never recomputed client-side (Phase 2's `cost_accounting.py` remains the single source).

**Resume-on-reconnect (a simplified version of decision-log #19's `Last-Event-ID` aspiration).** On every connection — first connect or reconnect — the route:
1. Reads all persisted `agent_run_steps` for the run from Postgres, in `sequence` order, and yields them as backfill.
2. If the backfill already contains a terminal step (`run_completed`/`run_failed`), or the run's own `status` is already terminal, the stream closes immediately — nothing will ever be published for a finished run, so no pub/sub subscription is opened at all.
3. Otherwise, it subscribes to `run:{run_id}:events` live, yielding new events as they arrive, and closes the stream the moment a terminal event type is observed.

This satisfies "a client reconnecting mid-run doesn't lose history" without implementing the HTTP `Last-Event-ID` header/cursor-based partial-replay protocol specifically — the full backfill is cheap at this phase's data volumes (one run's steps, not an unbounded history), and a genuine partial-resume-from-cursor optimization is deferred until a real client demands it (no speculative complexity, CLAUDE.md §16).

**Live event shape matches persisted shape, not a thinner notification.** An earlier draft of the worker executor published a thin `{"type": "step", "step_type": "llm_call"}` notification live (forcing a client to re-fetch from the DB to see actual content) while persisting the rich version. This was corrected before Phase 4 shipped: `apps/worker`'s `_record_and_publish_step` now persists and publishes the identical payload in one call, so there is exactly one representation of "what happened," not two that could drift.

**Disconnect cleanup.** The pub/sub subscription is unsubscribed and closed in a `finally` block around the live-streaming loop, covering both a clean terminal-event exit and a client disconnect (`asyncio.CancelledError` propagating through the generator) — `fastapi-expert`'s named failure mode (a leaked Redis subscription under load) is structurally avoided, not just tested for.

## Consequences

- A client can render live steps and a "replay so far" view with the same rendering code path — no dual schema to maintain.
- The full-backfill-on-every-connect approach means a client reconnecting to a very long-running run replays its entire history each time; acceptable at Phase 4's scale (single-agent-with-tools, bounded by `run_max_turns`/`run_timeout_seconds`), revisit if Phase 9+ orchestration produces much longer traces.
- Genuine OpenTelemetry distributed tracing (W3C `traceparent` propagation, span hierarchy) is **not** implemented as part of this ADR — see the "Known gap" note below.

## Known gap: no OpenTelemetry instrumentation yet

CLAUDE.md Rule 18 requires trace context never be dropped across an async boundary, and roadmap Phase 4 names `opentelemetry-expert` as a required skill. As of this ADR, **no OpenTelemetry SDK is installed or configured anywhere in this codebase** — setting one up correctly (SDK bootstrap in both `apps/api` and `apps/worker`, `traceparent` injection into Redis Streams job payloads and pub/sub messages, span design for orchestration/tool/LLM calls, exporter/Collector configuration) is a real, dedicated infrastructure project, not a byproduct of one SSE route.

What exists today is **ID-based correlation, not distributed tracing**: `run_id` flows unchanged through the job payload, every `agent_run_steps` row, the pub/sub channel name, and (via `job_id_var`) structured worker logs — satisfying `logging-expert`'s "correlate via shared IDs" pillar, but not `opentelemetry-expert`'s span-hierarchy/context-propagation pillar. This is a disclosed gap, not a silent one: full OTel instrumentation is recommended as its own future milestone once a real trace-consuming surface (a dashboard, an incident-response need) exists to justify the investment, per CLAUDE.md's no-speculative-complexity principle.

## Addendum: browser consumption (Phase 4 M7)

Native `EventSource` cannot set an `Authorization` header, and this route requires a bearer token resolved from the workspace member's session — a constraint not fully visible until the frontend consumer was actually built. The resolution: `apps/web/app/api/runs/[runId]/stream/route.ts` is a same-origin Next.js Route Handler (`nextjs-expert`'s documented case for a route handler: auth-cookie handling a client can't do itself) that holds the browser's session cookie, resolves it server-side to the bearer token via the existing `getBearerToken` helper, and pipes the upstream SSE response body through unmodified — the browser's `EventSource` then talks to this same-origin proxy, never directly to `apps/api`.

`apps/web/lib/hooks/useAgentRunStream.ts` consumes that proxy. High-frequency step events are buffered in a `ref` and flushed into React state on a 150ms interval rather than `setState` per event (CLAUDE.md §6 React 19); a terminal step (`run_completed`/`run_failed`) triggers an immediate flush and closes the connection; unmount always closes the `EventSource` (no leaked browser-side connection, the client-side mirror of this ADR's server-side disconnect-cleanup guarantee).

## Alternatives Considered

- **WebSockets** — rejected per `decision-log.md` #20: over-engineered for a one-directional server→client stream; reserved for genuinely bidirectional needs (a future interrupt/steer-a-running-agent control).
- **Thin live-event notifications + client re-fetch** — rejected: doubles the request volume for no benefit once the persisted and published shapes were unified (see Decision above).
- **True `Last-Event-ID` cursor-based partial resume** — deferred, not rejected: full backfill is simpler and cheap enough at current run-length scale; revisit when it isn't.
