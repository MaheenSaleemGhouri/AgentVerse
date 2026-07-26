# Job Queue & Dead-Letter Policy

Owner: `system-designer` / `redis-expert` / `senior-backend-engineer` (`docs/roadmap.md` Phase 3, `CLAUDE.md` Rule 14: "Long-running agent execution is always a background worker job... every worker task is idempotent so redelivery can't double-execute or double-bill; every queue has a dead-letter queue and bounded retry").

This is the wire contract between the two services that touch the queue — `apps/worker` (the sole consumer) and `apps/api` (the sole producer at this phase, via `/internal/job-test/enqueue`). They share this document, never code (`CLAUDE.md` §5: no service imports another service's internal modules).

## Transport

Redis Streams with a consumer group, not Redis pub/sub and not a list-based queue:

- **Durable** — messages persist in the stream until explicitly trimmed (not yet done at this phase; see "Known gaps" below), so a worker restart doesn't lose queued work the way pub/sub would.
- **At-least-once delivery with acknowledgment** — `XREADGROUP` + `XACK` means a message is only considered done once a consumer explicitly acks it, and `XPENDING`/`XAUTOCLAIM` let another consumer recover a message whose original reader crashed before acking.

## Keys

| Key | Purpose | Default value |
|---|---|---|
| `queue:jobs` | The main stream. Producers `XADD` here; workers consume via a consumer group. | `Settings.queue_stream` |
| `queue:jobs.dlq` | Dead-letter stream. Workers `XADD` here when a job exhausts its attempts or names an unknown `job_type`. | `Settings.queue_dlq_stream` |
| `workers` | The consumer group name shared by every worker process/replica. | `Settings.queue_group` |

Both `apps/api` (`infrastructure/config.py`) and `apps/worker` (`infrastructure/config.py`) default `queue_stream` to the literal string `"queue:jobs"` independently — this is the one string that must never drift between the two services' defaults without updating both.

## Field schema (main stream)

Every message on `queue:jobs` has exactly these string fields (the Redis client on both sides is constructed with `decode_responses=True` — every field is `str`, never `bytes`):

| Field | Type | Meaning |
|---|---|---|
| `job_id` | UUID string | Logical job identity, stable across retries (the stream message ID changes on each republish; `job_id` does not). |
| `job_type` | string | Dispatches to a handler. Phase 3 defined `"echo"`; Phase 4 adds `"agent_run"`. An unrecognized `job_type` is dead-lettered immediately (see below) — retrying it can never succeed. |
| `payload` | JSON string | Arbitrary handler input. For `echo`, a `force_fail: true` key makes the handler always fail — the mechanism the internal test endpoint uses to exercise retry/DLQ on demand. For `agent_run`, a single `run_id` key — the handler reads everything else (agent config, prompt) from Postgres via that ID, rather than duplicating it into the job payload. |
| `attempt` | string int, 0-based | How many times this job has already been attempted. `0` on first delivery. |
| `max_attempts` | string int | Bound on total attempts (not retries — `max_attempts=3` means 1 initial attempt + up to 2 retries). |

### Field schema (DLQ stream)

| Field | Meaning |
|---|---|
| `job_id`, `job_type`, `payload` | Same as above, carried through unchanged. |
| `attempts_made` | Total attempts actually made before giving up. |
| `failure_reason` | The last handler error, or `unknown_job_type:{type}` for a dispatch failure. |
| `failed_at_ms` | Unix epoch milliseconds when it was dead-lettered. |

## Retry policy

- Bounded exponential backoff with jitter: `delay = min(base_delay * 2^attempt, max_delay) + random(0, delay * 0.25)`. Defaults: `base_delay=0.5s`, `max_delay=8.0s` (`Settings.queue_base_delay_seconds` / `queue_max_delay_seconds`), tunable per environment.
- A handler failure acks the failed message (removing it from the pending list) and republishes a fresh message with `attempt` incremented — retries are new stream entries, not stream-native delayed delivery (Redis Streams has no native "deliver after N seconds" primitive).
- Once `attempt + 1 >= max_attempts`, the job is dead-lettered instead of retried.
- An unrecognized `job_type` is dead-lettered on the **first** delivery, with zero retries — retrying a dispatch failure can never succeed and would only waste attempts.

### Known gap: the backoff delay window is not durable

The delay between "handler failed" and "retry republished" is an in-process `asyncio.sleep`, not a Redis-native delayed queue. If the worker process crashes during that sleep, the scheduled retry is lost — the failed attempt was already acked (removed from pending), so no other consumer will pick it up either. This is an accepted limitation for this phase's proof-of-concept scope, not a silent gap:

- **Blast radius**: bounded to whatever's mid-backoff at the exact moment of a crash — typically zero to a handful of jobs, not the whole queue.
- **A future hardening path** (not built now — no concrete need yet, `CLAUDE.md`'s no-speculative-complexity rule): a Redis sorted set keyed by "due timestamp," polled by the consumer loop instead of an in-process timer, would make the retry's *scheduled* state durable too. Revisit if Phase 4+ real agent-run retries need this guarantee.

## Crash recovery vs. explicit retry — the distinction that matters

`docs/roadmap.md`'s own Risk section for this phase names this as the likely bug: conflating "a previous consumer died mid-handler without acking" with "the handler explicitly returned failure."

- **Crash recovery**: `XAUTOCLAIM` reclaims a message that's been pending longer than `queue_visibility_timeout_ms` (default 30s) with no ack — meaning whichever consumer read it never got the chance to finish or fail cleanly. Reprocessing this does **not** increment `attempt`; from the job's perspective, nothing about the business outcome happened yet.
- **Explicit retry**: the handler ran to completion and returned failure. This **does** increment `attempt` and is what drives the backoff/DLQ decision.

Unit tests in `apps/worker/tests/queue/test_redis_stream_queue.py` assert this distinction directly (`test_crashed_consumers_message_is_reclaimed_and_processed_once`).

## Idempotency

The job queue itself does not deduplicate — enqueueing the same logical operation twice produces two stream entries. Preventing that duplicate submission in the first place is `apps/worker/src/agentverse_worker/locks/distributed_lock.py`'s job (`SET NX PX` + a safe, token-checked release), taken out **before** enqueueing by whichever caller wants "at most once" semantics for a given logical key. Phase 3 proves the lock primitive in isolation; Phase 4's run-submission endpoint is its first real consumer.

## Observability

`GET /internal/queue/metrics` on `apps/worker` (not `/api/v1`, not internet-routable — this service has no public surface at all) reports:

```json
{"depth": 0, "pending": 0, "dlq_depth": 0}
```

- `depth` — `XLEN` on the main stream. Note this counts **every entry ever added**, not just unprocessed ones — this phase does not trim the stream (another known gap; retention policy is a later-phase concern once real volume exists).
- `pending` — in-flight/un-acked count via `XPENDING` summary form.
- `dlq_depth` — `XLEN` on the DLQ stream.

`apps/worker`'s `/ready` route additionally pings Redis directly — a queue with zero depth but an unreachable Redis is not "empty," it's "down," and the two must not be conflated.
