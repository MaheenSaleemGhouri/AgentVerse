# ADR-0018: Enterprise Dedicated Worker Routing

## Context

`docs/roadmap.md`'s Phase 12 calls for a dedicated-infrastructure option for Enterprise workspaces. An audit confirmed the plan-catalog metadata for this already existed and was unused: `Capability.PRIORITY_QUEUE` and `Capability.DEDICATED_INFRASTRUCTURE` are real enum members, seeded onto plan rows, but nothing in the codebase read either one — every workspace's runs, regardless of plan, land on the single global Redis stream (`queue:jobs`) and single consumer group (`workers`) `apps/worker/.../queue/factory.py` has always used.

Two things had to be decided: how a second worker fleet is expressed without duplicating the queue implementation, and how a workspace's entitlement is checked without turning a billing-side lookup into a new way for a run to fail outright.

## Decision

### A second stream/DLQ/consumer-group triad, not a second queue system

`RedisStreamQueue` already takes `stream`/`dlq_stream`/`group` in its constructor with no assumption baked in that there is only ever one instance. `apps/worker`'s `Settings` gained `queue_stream_priority` (`queue:jobs.priority`), `queue_dlq_stream_priority` (`queue:jobs.priority.dlq`), and `queue_group_priority` (`workers-priority`) alongside the existing shared-pool triad, plus a `worker_pool: Literal["shared", "priority"]` setting (env `AGENTVERSE_WORKER_WORKER_POOL`, default `"shared"`) that selects which triad *this process instance* binds to. `build_queue()` resolves `stream`/`dlq_stream`/`group` once at construction from that setting and passes the resolved values into `RedisStreamQueue(...)` — same handler dict (`echo`, `agent_run`, `kb_ingest`, `team_session`, `workflow_node`), same code path, a second deployed instance of the identical worker image consuming a different stream (CLAUDE.md §16 — no unnecessary complexity: not a new queue *system*, a second instance of the existing one).

`_workflow_node_handler`'s `WorkflowExecutionDeps.queue_stream` is bound to the resolved `stream` local, not unconditionally to `settings.queue_stream` — a workflow node executing on the priority pool must re-enqueue its own follow-on node onto the priority stream too, or a multi-node workflow would silently fall back to the shared queue after its first node, quietly defeating the whole point of the priority pool partway through a run.

### `require_capability`: a routing decision, not a security gate — resolves to `bool`, never raises

`auth_service/interface/dependencies/require_capability.py` is a new dependency factory, sibling to `require_role.py` but answering a different kind of question. `require_role` denies-by-default because a permission ceiling is a security boundary — refusing to raise there would be a vulnerability. `require_capability(capability)` is not that: it decides which of two already-authorized queues a request's run lands on, and an entitlement-lookup failure (a billing-side DB hiccup) must not turn into a run failure for what is, from the requester's perspective, an infrastructure question they have no way to route around. It wraps `EntitlementService.grants(...)` in `try/except Exception: return False`, matching the same best-effort/fail-open shape `UsageService.record_quietly` already uses for a structurally identical reliability-over-strictness boundary — a lookup failure resolves to "not entitled," never propagates.

### API-side: `get_run_producer` resolves the stream once per request, at the submission routes only

A new dependency (`orchestration_service/interface/dependencies/services.py`) composes `Depends(require_capability(Capability.PRIORITY_QUEUE))` with `settings.queue_stream_priority`/`settings.queue_stream` and returns a `JobQueueProducer` already bound to the right one. `agents.py`'s `submit_run_route` and `workflow_runs.py`'s `trigger_workflow_route` — the two places a run is first admitted onto a queue — take this in place of the plain `get_job_queue_producer` singleton. `apps/api`'s `Settings` gained the matching `queue_stream_priority` setting (same wire-contract discipline as `queue_stream` itself: the value must agree with apps/worker's setting of the same name, never imported across the service boundary).

Deliberately scoped to submission only, not `resolve_approval_route`'s follow-on-node enqueue: the plan's scope line is the run/workflow-*submission* routes, and re-deriving the workspace's entitlement on every subsequent approval-resolution call for a routing decision that only matters at admission time would be complexity without a proportionate benefit — a workflow's own priority-pool routing, once submitted, is carried forward by the worker-side `queue_stream` propagation described above, not re-decided per node.

`get_run_producer` is deliberately not `@lru_cache`'d like `get_job_queue_producer` — the stream it binds to is a per-request decision (today's entitlement, not a process-wide constant); only the underlying Redis client it wraps (itself cached) is actually shared.

## Consequences

- A priority-pool worker fleet is the same container image as the shared fleet, differentiated only by one env var at deploy time (`AGENTVERSE_WORKER_WORKER_POOL=priority`) — twelve-factor config, no code branch (CLAUDE.md §12).
- An Enterprise workspace's runs are only ever routed to the priority stream if a second `worker_pool="priority"` fleet is actually deployed and consuming it; until then, `queue:jobs.priority` simply accumulates unconsumed entries. This ADR does not claim a live second fleet is deployed — see `docs/deployment/worker-pools.md` for what is and isn't running today.
- An entitlement-lookup failure degrades gracefully to the shared stream rather than blocking a run outright — priority routing is best-effort, never a hard dependency for a run to succeed.
- No new Postgres tables or columns: `Capability.PRIORITY_QUEUE` already existed and is read for the first time here, not introduced.

## Alternatives considered and rejected

- **A second queue implementation (e.g. a priority field on the existing stream, consumed via `XCLAIM` ordering).** Rejected: Redis Streams has no native priority-dequeue primitive: a single stream with a priority field would need consumer-side logic to skip/reorder entries, which is materially more complex than, and offers no isolation benefit over, a second physical stream a dedicated fleet consumes exclusively — the actual goal (contention isolation for Enterprise runs) is what a second stream/fleet gives directly.
- **Gating priority routing with `require_role`'s deny-by-default shape (raise on non-entitlement).** Rejected: would turn a routing preference into an availability risk — a transient billing-lookup failure refusing the run itself, not just its queue placement, is a worse failure mode than falling back to the shared queue.
- **Re-checking entitlement on every workflow node's follow-on enqueue.** Rejected: adds a DB round-trip and a second decision point per node for no behavior difference from propagating the run's already-resolved stream forward, which `WorkflowExecutionDeps.queue_stream` already does.
- **Provisioning a live second Render worker service as part of this change.** Rejected for this ADR: no cloud credentials exist in this environment to provision it, and CLAUDE.md/the platform's own non-negotiable rules forbid claiming infrastructure capability that isn't actually deployed. The config surface (`worker_pool`, the priority triad) is real and functional; the second fleet's actual deployment is documented as the next concrete step in `docs/deployment/worker-pools.md`, not silently assumed.
