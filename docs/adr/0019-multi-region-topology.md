# ADR-0019: Multi-Region Topology

## Context

`docs/roadmap.md`'s Phase 12 calls for multi-region readiness. This environment has no cloud credentials to actually provision a second region — and CLAUDE.md's Rule 20 and the platform's own non-negotiable rules forbid claiming infrastructure capability that is not real. This ADR does two things a documentation-only deliverable can do honestly: state the target topology this codebase is designed toward, and draw the one boundary that makes "multi-region" a bounded, achievable target rather than an open-ended rewrite — never active-active multi-write Postgres.

`docs/deployment/multi-region-readiness.md` is the companion doc stating plainly what is and isn't deployed today; this ADR is the architecture decision, not the status report.

## Decision

### Target topology: global routing → regional API/worker pairs → single-primary Postgres with read replicas

A request enters through a global routing layer (DNS/anycast or a CDN's edge routing — the specific product is a `cloud-architect`/`infrastructure-engineer` decision at provisioning time, not fixed here) that sends it to the nearest healthy region. Each region runs a full `apps/api` + `apps/worker` deployment — the same container images every region runs, differentiated only by `AGENTVERSE_API_REGION`/`AGENTVERSE_WORKER_REGION`-equivalent config (twelve-factor, CLAUDE.md §12), never a code branch. Postgres stays **single-primary**: one region holds the writable primary, every other region's API/worker reads from a **read replica** in its own region for read-heavy traffic (dashboard queries, run history, marketplace browse) and forwards writes to the primary region over the network. Redis is region-local — it is cache/queue/coordination, never the system of record (Rule 13), so a region-local Redis with no cross-region replication is correct, not a gap.

### A workspace's system-of-record region is fixed at creation, never migrated silently

Every workspace is assigned a home region when it is created (a new `workspaces.region` column in the target design, defaulting to the single deployed region today). This is what keeps "single-primary with regional read replicas" coherent: a workspace's writes always route to its home region's primary, so there is one true order of writes for that workspace's data, and no distributed-consensus problem to solve. A workspace migrating regions (an enterprise customer with a data-residency requirement, say) is a deliberate, operator-driven data migration — not an automatic rebalancing this system performs on its own.

### Active-active multi-write Postgres is explicitly out of scope

Multiple regions accepting writes to the same logical data with automatic conflict resolution needs either a distributed SQL engine (CockroachDB, Spanner-alikes) or an application-level conflict-resolution strategy across every write path in this codebase (agent runs, billing events, audit logs — each with different correctness requirements for what "conflict" even means). That is a foundational rewrite of the data layer, not an increment on top of it, and CLAUDE.md §3's "Long-term Thinking" principle — build for today's requirement plus one known horizon, not speculative future-proofing — argues directly against building it before a concrete requirement (a specific enterprise SLA, a specific latency complaint) demands it.

### The one real increment shipped now: `AGENTVERSE_API_REGION`, surfaced on `/health`/`/ready`

`Settings.region: str = "primary"` (`apps/api/src/agentverse_api/infrastructure/config.py`) and the matching `HealthResponse.region` field, returned by both `/health` and `/ready` (`interface/routes/health.py`). This is deliberately small: it does not make the platform multi-region-capable by itself, but it is the first real, load-bearing piece — every other regional-awareness mechanism (routing health checks, region-scoped logging/tracing correlation, an eventual `workspaces.region` column) reads from the same setting, so it exists once, at the boundary, rather than being invented per-consumer later.

## Consequences

- No schema change ships with this ADR — `workspaces.region` is target design, not implemented. Adding it is additive (nullable or defaulted, per CLAUDE.md §8's migration discipline) whenever a second region is actually provisioned, not before.
- `docs/deployment/multi-region-readiness.md` must be kept honest as regions are actually added — a stale "not deployed" claim after a real second region ships would violate the same anti-overclaiming principle this ADR is written under.
- Nothing in `apps/worker`'s queue design (docs/adr/0018) conflicts with this: a region's worker fleet consumes its own region's Redis streams, same as today's single-region shared/priority split, just one more axis of "which instance consumes which stream."

## Alternatives considered and rejected

- **Active-active multi-write Postgres from the start.** Rejected: see Decision above — a distributed-SQL rewrite with no concrete requirement driving it yet, and the platform's every write path (billing especially, Rule 15) would need conflict-resolution semantics designed from scratch.
- **A single global Postgres primary with all regions reading and writing to it directly (no replicas).** Rejected as the *target*: it defeats the latency benefit multi-region exists for — a region without a local replica pays a cross-region round trip on every read, which is most of the traffic (dashboards, run history, marketplace browse).
- **Fabricating a second Render region in `render.yaml` to look "multi-region."** Rejected outright: no traffic would actually route there, no replica would actually exist, and CLAUDE.md forbids claiming capability that is not real. The honest, useful deliverable is the topology decision plus the one real config increment, stated as exactly that.
