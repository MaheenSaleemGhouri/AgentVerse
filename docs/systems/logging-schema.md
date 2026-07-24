# Structured Logging Schema

Owner: `logging-expert` (`CLAUDE.md` §12). This document is the schema contract; `infrastructure/logging.py` in `apps/api` and `apps/worker` is the implementation — if they ever disagree, fix the code or this doc, don't let them drift.

## Why JSON, why now

`CLAUDE.md` §7 prohibits `print()` and mandates structured JSON logging carrying correlation IDs via `contextvars`, "injected via request-scoped context... not threaded manually." Phase 0 has no business logic to log yet, but establishing the schema now means every log line emitted from Phase 1 onward is structured from its first commit — never a retrofit.

## Schema (Phase 0)

One JSON object per line, written to stdout (container log collection reads stdout, per twelve-factor):

| Field | Type | Present | Meaning |
|---|---|---|---|
| `timestamp` | ISO 8601 UTC string | always | `datetime.now(UTC).isoformat()` equivalent |
| `level` | string | always | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `logger` | string | always | Python logger name (module path) |
| `message` | string | always | Human-readable message |
| `request_id` | string | `apps/api` only, when bound | Set by `interface/middleware.py`'s request-scoped context var for the duration of one HTTP request; client-supplied via `X-Request-Id` or generated |
| `job_id` | string | `apps/worker` only, when bound | Reserved context var (`infrastructure/logging.py`); unused until Phase 3 introduces real jobs |
| `exception` | string | only on logged exceptions | Formatted traceback |

## Fields added in later phases (not yet implemented)

- `workspace_id` — bound as soon as Phase 1's `get_current_workspace` dependency resolves a request's tenant. Every log line inside a workspace-scoped request carries it.
- `run_id` — bound for the duration of an agent run's execution path, from Phase 4 onward.

These are additive: the `JSONFormatter` in both services already emits whatever keys are currently bound in its context vars, so adding a new correlation ID later is a context-var addition at the call site, not a formatter rewrite.

## Log level policy

- `DEBUG` — verbose, off by default (`AGENTVERSE_API_LOG_LEVEL=INFO` / `AGENTVERSE_WORKER_LOG_LEVEL=INFO` are the shipped defaults).
- `INFO` — default. Request lifecycle, job lifecycle (once jobs exist).
- `WARNING` — recoverable anomalies (e.g. a retried operation).
- `ERROR` — a request/job failed; always paired with `exception` when raised from a caught exception.

## PII / retention

No user data flows through this system yet (Phase 0 has no tenant data). Once Phase 1+ introduces real requests, `CLAUDE.md` §10's privacy rule applies: agent execution logs (prompts, tool I/O, completions) are treated as potentially containing customer PII by default, redacted in general logs, with full content only in a separate access-restricted, shorter-retention stream. This document will gain a concrete redaction rule set when the first PII-bearing field is logged (Phase 1's auth flows).
