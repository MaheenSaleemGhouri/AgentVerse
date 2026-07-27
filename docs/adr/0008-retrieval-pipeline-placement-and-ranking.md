# ADR 0008: Retrieval Pipeline Placement and Ranking Strategy

## Numbering note

`docs/roadmap.md`'s Phase 5 deliverables suggest this ADR at a lower number. Every number through `0007` is consumed (see the note in `0007-sse-run-streaming-contract.md` for the same documented-deviation pattern). Per ADR immutability discipline (CLAUDE.md §13), this is `0008`.

## Context

Phase 5 adds knowledge bases: documents are uploaded, chunked, embedded, and retrieved to ground an agent's answers with citations. Two design questions had to be settled before any of it could be written, and both cut across the constitution in ways that are not obvious from either side alone.

**1. Where does the retrieval pipeline live?**

`docs/roadmap.md` Phase 5 names `apps/api/.../application/retrieval/`. But two callers need retrieval, not one:

- `POST .../knowledge-bases/{id}/search` in apps/api — the "test this knowledge base" surface in the Knowledge UI.
- `ground_run()` in apps/worker — what an actual agent run uses.

If those two rank differently, the search preview becomes a debugging surface that lies: a user tunes their documents against results their agent will never see. That is a Rule 3 violation (one source of truth for logic used by more than one service) with a failure mode that produces no error at all.

`ADR-0003` chose pgvector inside the primary Postgres rather than a separate vector service. CLAUDE.md §5 says vector-DB access is encapsulated behind the agent-runtime fleet, which reads at first glance as forbidding apps/api from touching `kb_chunks` at all.

**2. How are the two retrieval arms combined?**

Hybrid retrieval means a semantic arm (pgvector `<=>` cosine distance) and a keyword arm (Postgres FTS `ts_rank_cd`). Their scores must be combined into one ranking.

## Decision

**Placement: `packages/python-shared/src/agentverse_shared/retrieval/`**, using the four module names the roadmap specifies (`rewrite.py`, `retrieve.py`, `rerank.py`, `assemble.py`) plus `pipeline.py` composing them, `port.py` defining `ChunkSearchPort`, and `postgres_search.py` as its one implementation.

The §5 tension resolves rather than conflicts: because ADR-0003 put vectors in the primary Postgres, `kb_chunks` is the orchestration service's *own* table. apps/api reading it is a service reading its own database — not a cross-service reach into another service's schema, which is what §5 prohibits. The rule that actually binds here is Rule 3, and it points the other way.

**Ranking: Reciprocal Rank Fusion (RRF), k = 60.**

Not a weighted score blend. Cosine similarity lives in [0, 1] with real values bunched near the top; `ts_rank_cd` is unbounded and corpus-dependent. Normalizing them into a shared range requires corpus statistics we would be guessing at, and a guessed blend looks principled without being so. RRF reads only *positions*, so it needs no calibration. k = 60 is the published default (Cormack et al. 2009) and is deliberately not hand-tuned — tuning it without an eval set is noise.

**Both arms filter on `embedding_model` and `embedding_model_version`,** not because keyword matching depends on the embedding, but so the two arms draw from *exactly* the same candidate pool. Fusing two differently-scoped pools produces meaningless ranks and raises nothing.

**Reranking is MMR-style greedy diversification using lexical Jaccard overlap, not a cross-encoder.** A cross-encoder would add a second model call to every run's latency and cost budget; adopting one is deferred until the eval set shows it earns its place (CLAUDE.md §9: each stage justified by measured improvement).

**Tenancy is a required argument on `ChunkSearchPort`,** so an adapter that forgot to filter by `workspace_id` cannot be written — the signature makes it a type error rather than a code-review catch (Rule 11).

**Grounding failure degrades a run; it never fails one.** An empty KB, a brief embedding-provider outage, a KB detached between publish and execution — the run proceeds ungrounded and emits a `retrieval` trace step carrying the error. An agent that answers without its documents is degraded; one that refuses to answer is broken. The step is always emitted when the agent has knowledge bases, so degradation is visible rather than silent.

**Retrieved content is appended as a delimited `<retrieved_context>` block, never merged into the instruction text** (CLAUDE.md §9/§10). Document content is untrusted input; a document containing "ignore previous instructions" must be visibly data.

## Consequences

- The search endpoint and a real agent run provably rank identically, because they call the same function.
- `packages/python-shared` now depends on `sqlalchemy[asyncio]` (Core only — it defines no tables and owns no metadata; apps/api's Alembic migrations remain the sole schema authority).
- A knowledge base indexed under an embedding identity the deployment no longer produces returns `409 Conflict` from the search endpoint ("reindex before searching") rather than silently comparing vectors across two embedding spaces.
- An agent attached to knowledge bases with *differing* embedding identities searches only the group matching the first one in its config order; the rest are skipped and named in the trace step's `skipped_knowledge_base_ids`.
- Ranking quality is now a CI gate: `packages/python-shared/tests/retrieval/eval/` scores a labelled dataset for recall@5, precision@5, and MRR against committed baselines. Current: recall@5 = 1.000, precision@5 = 0.352, MRR = 1.000 over 8 cases.

## Alternatives considered and rejected

- **Duplicate the pipeline in apps/api and apps/worker.** Rejected: the divergence failure mode is silent (worse rankings, no error), which is exactly the class of bug Rule 3 exists to prevent.
- **Put retrieval only in apps/worker and have apps/api call it over HTTP for search.** Rejected as speculative complexity (Rule 10): it introduces a synchronous inter-service hop to solve a problem a shared package solves with no runtime cost, and §5's constraint does not actually apply once ADR-0003's placement is accounted for.
- **Weighted score blending (α·cosine + β·ts_rank).** Rejected: not calibratable without corpus statistics we do not have.
- **Cross-encoder reranking.** Deferred, not rejected — revisit when the eval set can demonstrate the gain against the added latency and cost.
- **Post-filtering an unscoped top-k by `workspace_id`.** Rejected outright: leaks tenant data via timing/recall and degrades recall for the legitimate tenant (Rule 11, `vector-database-expert`).

## Addendum: the `retrieval` step type

Phase 5 adds one value to the `agent_run_steps.step_type` vocabulary ADR-0007 defines: `retrieval`. This is an **additive** contract change — no existing `type` value changes meaning or shape, so no `/v1` version bump is required (CLAUDE.md §7: error codes and event types are stable and additive once published). ADR-0007 is not edited; it remains the record of the decision as made.

Payload:

```json
{
  "type": "retrieval",
  "sequence": 2,
  "payload": {
    "citations": [{"chunk_id": "...", "kb_document_id": "...", "knowledge_base_id": "...", "chunk_index": 0}],
    "used_tokens": 412,
    "dropped_chunk_count": 1,
    "skipped_knowledge_base_ids": [],
    "error": null
  },
  "cost_micro_usd": null
}
```

Emitted once per run, before the first `llm_call`, and **only when the agent version has knowledge bases attached** — an agent with none would otherwise carry a noise step on every run saying nothing happened. When it is emitted it is always emitted, hit or miss or failure, so "why did my agent ignore my documents?" is answerable from the trace alone.

`apps/web`'s `RunStepType` union and `STEP_ICON` map are exhaustive over this vocabulary, so a future backend step type fails the frontend build until it is handled (CLAUDE.md §6).
