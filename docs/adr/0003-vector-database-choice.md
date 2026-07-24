# ADR-0003: Vector Database Choice — pgvector on the Primary Postgres Instance

## Context

`decision-log.md` #5 ("Why Vector Database") requires the vector DB choice to be made before Phase 5 (Knowledge Bases & RAG) can begin, while explicitly framing it as revisitable once Phase 5's real retrieval-latency/recall needs are known. `docs/roadmap.md` Phase 0 requires deciding it now — with zero consuming code — specifically so `infra/docker-compose.yml` has one authoritative datastore definition instead of every later phase guessing at local-dev topology. No `kb_chunks` table or embedding column exists yet; this ADR fixes the *infrastructure* choice only.

## Decision

Use the `pgvector` extension on the same Postgres instance that serves relational data (image: `pgvector/pgvector:pg16` in `infra/docker-compose.yml`), rather than standing up a separate dedicated vector database service. One instance, one connection pool, one backup/restore procedure. When Phase 5 introduces `kb_chunks`, its `embedding` column will be a `pgvector` column, `workspace_id`-scoped and pre-filtered per `CLAUDE.md` §8's vector-DB tenancy rule (not yet enforced — no vector column exists in Phase 0).

## Consequences

**Positive:** one fewer moving part in both local dev and production topology; transactional consistency is available between relational and vector data if a future feature needs it in the same transaction; one operational surface (backup schedule, connection pooling, monitoring) instead of two.

**Negative:** co-located workload risk — heavy vector search load at scale could contend with transactional Postgres load on the same instance; HNSW index build/maintenance shares the primary instance's CPU/memory budget. Neither risk is measurable yet (no vector workload exists), so this ADR treats it as a flagged, monitored risk rather than a blocker.

**Checkpoint:** revisit at the same `2026-10-01` window as ADR-0002, or sooner if Phase 5's retrieval-latency budget (`CLAUDE.md` §17) can't be met on the shared instance once real query patterns exist.

## Alternatives considered

- **Dedicated managed vector database (Pinecone, Qdrant, Weaviate, etc.).** Rejected for now: introduces a second datastore with its own backup/DR story, credential surface, and operational learning curve before any query pattern exists to justify it — directly against `CLAUDE.md` §3's "prefer boring, proven technology... over novel tools absent a concrete constraint." Revisit if the co-location risk above materializes with real data.
- **Separate self-hosted Postgres+pgvector instance, distinct from the primary transactional database.** Rejected: no current scale justifies splitting a single-instance workload that doesn't exist yet; this is the natural next step if ADR-0003's own flagged risk materializes, not a Phase 0 default.

## Review

**Status:** Approved
**Reviewer:** `architecture-reviewer` (via the AgentVerse Master AI Engineering Team coordination this ADR was authored under)
**Date:** 2026-07-24

Verified against `decision-log.md` #5's explicit framing of this choice as revisitable, and against `CLAUDE.md` §8's vector-DB tenancy rule (which this ADR correctly defers implementing until a vector column actually exists in Phase 5, rather than guessing at enforcement code now). The co-location risk in Consequences is a real, named, monitored risk rather than an unstated one. Approved without conditions; flagged for re-validation at the same `2026-10-01` checkpoint as ADR-0002, or sooner if Phase 5 can't meet its retrieval-latency budget on this topology.
