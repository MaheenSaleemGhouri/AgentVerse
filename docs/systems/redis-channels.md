# Redis Pub/Sub Channel Conventions

Owner: `redis-expert` / `system-designer` (`docs/roadmap.md` Phase 3: "Redis pub/sub channel convention `run:{run_id}:events` established as **infra-only scaffolding**").

## Status: scaffolding only — not yet consumed by any client

This document reserves the naming convention for the channel Phase 4's live execution-trace streaming will use. As of Phase 3, **no code publishes or subscribes to this channel** — there is no `run` concept anywhere in the codebase yet (Phase 3's queue proves mechanics against a trivial echo job, not a real agent run).

This is a deliberate ordering decision, not an oversight: `decision-log.md` #19 ("Why SSE") already committed to "FastAPI serves it via `StreamingResponse` reading from Redis pub/sub" as the transport for live execution traces. Building the channel *name* now, while the queue infrastructure is already being designed, avoids a later rename; building the channel's actual *event schema* now, before a real consumer exists to validate it against, risks guessing wrong and having to break it. `docs/roadmap.md`'s own Risk section for this phase names this explicitly:

> Building the pub/sub channel convention this early without a real SSE consumer risks guessing the wrong event shape — mitigate by treating it as a naming/scaffolding decision only, deferring the actual event schema to Phase 4 where a real consumer exists.

## The convention (name only)

```
run:{run_id}:events
```

- `{run_id}` — the opaque ID (ULID/UUID, per `CLAUDE.md` §7 REST APIs convention) of an `agent_runs` row, once that table exists (Phase 4).
- One channel per run, not a global fan-out channel — so a client subscribing to its own run's events never receives another workspace's traffic, and the channel naturally stops mattering once the run completes (no long-lived subscription to clean up beyond the run's own lifetime).

## What is explicitly NOT decided here

- The event payload shape (what a "step started" / "token" / "tool call" / "step completed" message actually contains).
- Whether publish happens directly from the worker process or via an intermediate event bus.
- Retention/replay semantics for a client that reconnects mid-run (`decision-log.md` #19 notes SSE's `Last-Event-ID`-style resume as the target behavior, but the concrete mechanism is a Phase 4 design task).
- Any FastAPI route consuming this channel via `StreamingResponse`.

All of the above are Phase 4 (`Single-Agent Builder, Runtime & Live Execution (SSE)`) design tasks. Reserving the name now does not authorize building the rest early.
