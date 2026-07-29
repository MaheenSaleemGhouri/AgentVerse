# Latency budgets — MCP integrations and tool execution

`CLAUDE.md` §17 requires a published budget before an endpoint ships, and
§19 item 6 requires a measured actual within it. This document is the
first half. **The measurement has not been taken** — see the last
section, which says so plainly rather than leaving it inferred.

Owner: `performance-engineer` (budgets and diagnosis). Fixes, if a budget
is breached, are `optimization-expert`'s.

## Why tool calls need their own budgets

The platform-wide endpoint-class budgets do not fit here. A tool call's
latency is dominated by a third party we do not control — a GitHub API
round trip, someone's self-hosted MCP server. Holding it to a CRUD budget
would fail constantly for reasons no fix addresses.

So the budgets below split into two kinds, and the split is the point:

- **AgentVerse-controlled** — everything the boundary does before and
  after the external call. Breaching this is our bug.
- **End-to-end** — includes the third party. Breaching this is
  information, not necessarily a defect, and it routes to the
  circuit breaker rather than to an engineer.

Reporting only the second number is the mistake §17 warns about:
optimising our code when 90% of the time is someone else's network.

## Read endpoints

Ordinary API traffic, no external call. Measured at the gateway,
excluding client network.

| Endpoint | p50 | p95 | p99 | Note |
| --- | --- | --- | --- | --- |
| `GET /integrations/catalog` | 40 ms | 120 ms | 250 ms | ~38 rows, no join to installs |
| `GET /integrations` | 50 ms | 150 ms | 300 ms | Includes each install's cached tool list |
| `GET /integrations/{id}` | 40 ms | 120 ms | 250 ms | |
| `GET /integrations/{id}/credentials` | 30 ms | 90 ms | 200 ms | Metadata only — no unseal, so no KMS cost |
| `GET /integrations/{id}/permissions` | 30 ms | 90 ms | 200 ms | |
| `GET /tool-calls` (cursor page of 50) | 60 ms | 200 ms | 400 ms | Partitioned table, `(workspace_id, created_at DESC)` |
| `GET /integrations/metrics` | 80 ms | 300 ms | 600 ms | Aggregates live over `tool_calls` — see the scaling note |

**Scaling note on metrics.** That endpoint computes counts and p95 live
from `tool_calls`. Correct, and fine at current volume; it will not hold
at a workspace with millions of rows. The `tool_metrics` rollup table
exists for this and its aggregation job does not — recorded as gap 5 in
the Phase 6 checklist. The budget above assumes a workspace under roughly
100k tool calls; past that, the rollup is required, not optional.

## Write endpoints

| Endpoint | p50 | p95 | p99 | Note |
| --- | --- | --- | --- | --- |
| `POST /integrations` (install from catalog) | 60 ms | 180 ms | 350 ms | One insert; no network |
| `POST /integrations/custom` | 200 ms | 600 ms | 1200 ms | Includes a DNS resolution and egress validation before accepting the endpoint — deliberately synchronous, since accepting an unroutable URL and failing later is worse |
| `PUT /integrations/{id}/credentials` | 80 ms | 250 ms | 500 ms | Includes AES-256-GCM seal; the KEK is in-process, so no network |
| `DELETE …/credentials/{key}` | 50 ms | 150 ms | 300 ms | |
| `POST /integrations/{id}/permissions` | 50 ms | 150 ms | 300 ms | |

## Tool execution

The number that matters, split as described above.

| Segment | p50 | p95 | p99 | Breach means |
| --- | --- | --- | --- | --- |
| **Boundary overhead** (breaker + permission + arg validation + budget + cache + sanitise) | 8 ms | 25 ms | 50 ms | **Our defect.** This is pure compute plus a few Redis round trips |
| Cache hit, end to end | 10 ms | 30 ms | 60 ms | Our defect |
| Refusal (denied / circuit open), end to end | 12 ms | 35 ms | 70 ms | Our defect. A refusal must be *cheap* — it is the path an attacker exercises repeatedly |
| **End to end, cache miss** | 400 ms | 2500 ms | 8000 ms | Third-party-dominated. Informational |
| Hard ceiling | — | — | 120 s | `MAX_TIMEOUT_SECONDS` in the boundary. Not a budget — a cutoff |

**Refusals are budgeted deliberately.** A denied call that took as long
as a real one would turn the permission check into an amplifier: an
injected instruction fires a hundred refused calls and each still costs a
round trip. The ordering in `execute_tool` — breaker, then permission,
then validation, then budget, then cache, then the network — exists so
that the cheapest rejection happens first.

## Frontend

| Surface | LCP | INP | CLS |
| --- | --- | --- | --- |
| `/integrations` | 2.0 s | 200 ms | 0.1 |
| `/integrations/{id}` | 2.0 s | 200 ms | 0.1 |
| `/mcp` | 2.5 s | 200 ms | 0.1 |

Route JS from the production build, as a starting budget — a regression
beyond +15% should be investigated:

| Route | First load JS |
| --- | --- |
| `/dashboard/[workspaceId]/integrations` | 195 kB |
| `/dashboard/[workspaceId]/mcp` | 230 kB |

Marketplace filtering is client-side over the already-fetched catalog
deliberately: ~38 rows, and a request per keystroke would cost more than
the filter saves.

## What has not been measured

**No numbers above are observed.** They are budgets derived from the work
each path does — the reasoning is stated per row so a wrong assumption is
arguable rather than hidden.

Specifically not done:

1. **No load test.** The circuit breaker and per-run budget are
   unit-tested for behaviour, never measured under concurrency (Phase 6
   checklist gap 6).
2. **No `EXPLAIN (ANALYZE, BUFFERS)` at realistic scale.** The indexes
   were designed for these access patterns and verified against a small
   local dataset. §8 requires realistic volume, and that has not happened.
3. **No CI performance gate.** §17 requires one so a regression class
   cannot silently return. Lighthouse CI and a bundle-size budget are not
   wired up.
4. **No p50/p95/p99 telemetry in production**, because there is no
   production.

Until at least 1 and 3 exist, `CLAUDE.md` §19 item 6 is **not
satisfied** — a budget without a measurement is a hypothesis.
