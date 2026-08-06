# Rollback: apps/worker

## The action

```bash
coolify deploy --service agentverse-worker --image ghcr.io/agentverse/worker:sha-<previous>
```

## Before you roll back: what is mid-flight?

The worker consumes a Redis Stream with consumer groups, and this is the
part a naive rollback gets wrong.

- **In-flight jobs are not lost.** An unacknowledged message returns to
  the pending list and is redelivered to the next consumer. Rolling back
  mid-job is safe for that reason.
- **Every task is idempotent** (Rule 14), so redelivery cannot
  double-execute or double-bill. Usage events carry a key derived from
  the run, so a re-run records nothing new.
- **The dead-letter queue is where poison messages go.** A job failing
  repeatedly across a rollback is a bad message, not a bad deploy —
  check the DLQ before assuming the new image caused it.

Draining is readiness-gated, so in-flight requests and SSE connections
finish rather than dropping.

## Symptom → diagnosis

| Symptom | First check |
|---|---|
| Queue depth climbing | Consumers are down or wedged. Check `/ready` and the consumer-group lag. |
| `CredentialUnsealFailure` alert | `AGENTVERSE_CREDENTIAL_KEK_V1` differs between api and worker — the common cause, usually right after a deploy where one service got the new value and the other did not. |
| `EgressDenied` alert | Not a deploy problem. The guard blocked an outbound call *before* connecting; nothing was reached. See `docs/observability/tool-execution-monitoring.md`. |
| Metrics missing entirely | The worker must run a single uvicorn process. `--workers N` scrapes one of N and undercounts silently. |

## Escalation

Queue mechanics → `system-designer`. Tool execution → `mcp-expert`.
