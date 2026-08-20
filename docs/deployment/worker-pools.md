# Worker Pools — Shared vs. Priority

See `docs/adr/0018-enterprise-dedicated-worker-routing.md` for the design rationale. This doc states the config shape and, per that ADR's own scope line, what is and isn't actually deployed.

## Status

`apps/worker`'s priority-pool config (`queue_stream_priority`, `queue_dlq_stream_priority`, `queue_group_priority`, `worker_pool`) and `apps/api`'s corresponding routing dependency (`get_run_producer`) are implemented and tested against `fakeredis`/in-process fakes. **No second worker fleet is deployed anywhere.** Every run today — Free through Enterprise — is still processed by the single shared fleet described in `docs/deployment/vercel-production.md`'s "not deployed anywhere yet" status for `apps/api`/`apps/worker`. An Enterprise workspace granted `Capability.PRIORITY_QUEUE` will have its runs enqueued onto `queue:jobs.priority`, but nothing consumes that stream until a `worker_pool="priority"` instance is actually running — the entries simply accumulate until one is deployed. This is a config surface ready for the next real deploy step, not a live capability.

## Config shape

Both pools run the identical `apps/worker` container image; only the environment differs (twelve-factor: no code branch on which pool a process belongs to).

| Setting | Shared (default) | Priority |
|---|---|---|
| `AGENTVERSE_WORKER_WORKER_POOL` | `shared` (or unset) | `priority` |
| Stream consumed | `queue:jobs` | `queue:jobs.priority` |
| DLQ stream | `queue:jobs.dlq` | `queue:jobs.priority.dlq` |
| Consumer group | `workers` | `workers-priority` |

`apps/api`'s `AGENTVERSE_API_QUEUE_STREAM_PRIORITY` must agree with `apps/worker`'s `AGENTVERSE_WORKER_QUEUE_STREAM_PRIORITY` (both default to `queue:jobs.priority`) — this is a wire-contract value, not shared code, matching how `queue_stream` itself already works across the two services.

## Provisioning a live priority fleet (next step, not yet done)

1. Deploy a second `apps/worker` process (a second Render/Railway/Coolify service, or a second replica group in whatever host is eventually chosen per `vercel-production.md`) from the same image, with `AGENTVERSE_WORKER_WORKER_POOL=priority` set and every other env var identical to the shared fleet (same `DATABASE_URL`, same `REDIS_URL` — both pools share the same Postgres and the same Redis instance, only the stream/group differs).
2. Scale it independently of the shared fleet's replica count — the entire point of a dedicated pool is that Enterprise runs are never queued behind the shared fleet's contention, so its capacity should track Enterprise workspace count/run volume, not the platform's aggregate run volume.
3. No API-side change is needed to start routing traffic to it: `get_run_producer` already enqueues onto `queue:jobs.priority` for any workspace `EntitlementService.grants(...)` resolves `Capability.PRIORITY_QUEUE` for, the moment that stream has a consumer.
