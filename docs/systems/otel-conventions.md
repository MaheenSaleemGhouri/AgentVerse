# OpenTelemetry Wiring Conventions

Owner: `opentelemetry-expert` (`CLAUDE.md` §4/§9/§20 Rule 18: "Every agent run is one connected trace... trace context is explicitly propagated across every async/queue boundary, and dropping it is a bug").

## Phase 0 scope

No spans are emitted yet — there is no orchestration step, tool call, or LLM call to trace. This document fixes the *naming and propagation conventions* every later phase must follow, so tracing is designed in from Phase 1 onward rather than bolted on once multiple services already disagree on span names.

## Conventions (to be implemented starting Phase 1)

**Service naming.** OTel `service.name` resource attribute matches the service's package name exactly: `agentverse-api`, `agentverse-worker`, `agentverse-web`. These already exist as `Settings.service_name` defaults in both Python services' `infrastructure/config.py` — the OTel SDK setup (when it lands) reads from there, never a second hardcoded string.

**One trace per agent run.** From Phase 4 onward, every `run` gets exactly one trace, spanning API → orchestration → worker → tool call → LLM call, with correct parent/child span nesting (`CLAUDE.md` §4 Tracing). The trace's root span starts when a run is submitted (`POST /api/v1/.../runs`) and ends when the run reaches a terminal state.

**Span naming pattern.** `<domain>.<action>` — e.g. `run.step`, `tool.call`, `llm.call`, `workflow.node.execute` (Phase 10). Attributes carry the correlating IDs already established in `docs/systems/logging-schema.md`: `workspace_id`, `run_id`, and (Phase 10+) `workflow_id`.

**Context propagation across boundaries.** Trace context must survive the one boundary that silently drops it most often: the Redis-backed job queue between `apps/api` and `apps/worker` (Phase 3). The job payload carries the trace context explicitly (W3C `traceparent` format) — a worker picking up a job starts its span as a child of the enqueuing request's span, not a new disconnected trace. This is the single highest-risk convention to violate; `opentelemetry-expert` reviews the Phase 3/4 queue payload schema specifically for this.

**Correlation with logs.** Every span-scoped log line (once OTel is wired) includes the active `trace_id`/`span_id`, alongside the `request_id`/`job_id` fields `docs/systems/logging-schema.md` already defines — logs and traces correlate by shared IDs, never merged into one pillar (`CLAUDE.md` §5 Separation of Concerns).

## What is explicitly deferred

Actual OTel SDK instrumentation (`opentelemetry-sdk`, exporter configuration, FastAPI/Starlette auto-instrumentation) is not installed in Phase 0 — there is nothing to trace yet, and adding the SDK now would be dead weight until Phase 1+ gives it real spans to emit. This document exists so that when it *is* added, every service follows the same naming and propagation rules from the first span.
