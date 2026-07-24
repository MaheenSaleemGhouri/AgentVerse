# Health & Readiness Contract

Owner: `observability-engineer` / `principal-software-architect` (`CLAUDE.md` §12: "Every service exposes `/health` (liveness) and `/ready` (readiness) with correct distinct semantics before it can receive traffic").

## Contract

Every AgentVerse service — `apps/web`, `apps/api`, `apps/worker`, and every service added in later phases — implements exactly these two routes before any business route:

| Route | Semantics | Checks | Failure meaning |
|---|---|---|---|
| `GET /health` (or `/api/health` for `apps/web`) | **Liveness** — is the process up and able to respond at all | Nothing external; a 200 response *is* the check | Orchestrator should restart the container |
| `GET /ready` (or `/api/ready` for `apps/web`) | **Readiness** — are this service's hard dependencies reachable | Nothing yet (Phase 0: no service has a hard dependency wired in) | Orchestrator should stop routing traffic here, but not restart |

Both return `{"status": "ok"}` with HTTP 200 when healthy. A future failure mode returns a non-200 status — no service currently has a failure path to exercise, since none has a real dependency check yet.

## Current state per service (Phase 0)

- **`apps/web`** (`app/api/health/route.ts`, `app/api/ready/route.ts`): both routes return `ok` unconditionally. `apps/web` has no hard runtime dependency in Phase 0 (it never calls `apps/api`), so readiness currently reduces to liveness — documented in each route file's own comment.
- **`apps/api`** (`interface/routes/health.py`): same — no Postgres/Redis dependency is consumed by any code path yet, so `/ready` reduces to `/health`.
- **`apps/worker`** (`interface/routes/health.py`): same pattern, on port 8001.

## What changes in later phases

- Phase 1: `apps/api`'s `/ready` gains a real Postgres connectivity check (the workspace/RBAC schema is the first thing that must be reachable).
- Phase 3: `apps/worker`'s `/ready` gains a real Redis connectivity check (the job queue is the first hard dependency).

When either lands, only that route handler's body changes — the contract (route path, response shape, liveness-vs-readiness meaning) does not.

## Docker Compose wiring

`infra/docker-compose.yml` uses these routes as `healthcheck` targets and gates `depends_on: condition: service_healthy` across the dependency chain: `postgres`/`redis` → `api`/`worker` → `web`. See `infra/README.md` for the exact ordering.
