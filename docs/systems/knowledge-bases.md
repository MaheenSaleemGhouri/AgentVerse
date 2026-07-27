# Knowledge Bases & Retrieval (Phase 5)

How a document becomes a citation. Decisions are recorded in [ADR 0008](../adr/0008-retrieval-pipeline-placement-and-ranking.md) and [ADR 0003](../adr/0003-vector-database-choice.md); this page is the operational map.

## Data model

Owned by the orchestration service, migrated by `apps/api`'s Alembic (`56f9a66678b2`). Every table carries `workspace_id` with a leading index (Rule 11).

| Table | Purpose |
| --- | --- |
| `knowledge_bases` | A workspace-scoped collection. Pins `embedding_model` / `embedding_model_version` **at creation** — a later platform default change must never reinterpret existing vectors. Soft-deleted via `deleted_at`. |
| `kb_documents` | One uploaded file. `storage_key` is generated, never the client's filename. `content_hash` is the SHA-256 of the *extracted text* and is what makes ingestion idempotent. `status` ∈ `pending → processing → indexed \| failed`. |
| `kb_chunks` | One retrievable unit: `content`, `token_count`, `embedding vector(1536)`, plus the `embedding_model`/`embedding_model_version` that produced it. HNSW index on `vector_cosine_ops`; GIN index on `to_tsvector('english', content)`. Unique on `(kb_document_id, content_hash, chunk_index)`. |

`agents.config.knowledge_base_ids` attaches KBs to an agent. It is part of the **versioned** config, so a published version's grounding sources cannot change retroactively.

## Upload path (apps/api)

`POST /api/v1/workspaces/{ws}/knowledge-bases/{kb}/documents` → `202 Accepted`.

1. **Size cap first**, before anything is read into a parser (`max_document_bytes`, default 25 MB).
2. **Resolve the KB scoped to the authenticated workspace.** Not found ⇒ `404`, never `403` — a cross-tenant id must be indistinguishable from a nonexistent one.
3. **Content-sniff on magic bytes**, never the declared MIME type or extension. PDF (`%PDF-`), DOCX (`PK\x03\x04` + `.docx`), or strict UTF-8 text. Recognised non-documents (PNG/JPEG/GIF/ELF/MZ/gzip/PostScript/legacy-OLE) are rejected by name so the user knows what they actually uploaded. Anything else ⇒ `422`.
4. **Write bytes, then create the row.** In that order deliberately: an orphaned file is inert, whereas a `pending` row with no file is ambiguous to the ingestion job — it cannot tell "not uploaded yet" from "lost".
5. **Enqueue `kb_ingest`.** Chunking and embedding are background work (Rule 14).

Files are stored outside any web-served directory under a generated key; nothing serves these bytes back over HTTP.

## Ingestion path (apps/worker)

`kb_ingest` job → extract → hash → chunk → embed → bulk insert.

- **Idempotent per `(kb_document_id, content_hash)`.** A redelivered job whose content hash is unchanged short-circuits before spending any embedding budget; `ON CONFLICT DO NOTHING` on the unique constraint is the database-level backstop. `POST .../reindex` clears the hash precisely so reindex means *redo*, not *re-enqueue and skip*.
- **Content-aware chunking**: ~500-token prose chunks with overlap, function/class-level for code, heading-bounded for markdown. Pure functions, unit-tested against a deterministic word counter.
- **Refuses to index when the KB's embedding identity differs from the embedder's** — mixing versions in one KB is a silent scoring failure, so it is a hard stop.
- Failures mark the document `failed` with a truncated `error_message` surfaced in the UI. Partial chunks are never left behind.

## Retrieval path (`packages/python-shared/agentverse_shared/retrieval/`)

One implementation, two callers — the search endpoint and a real agent run rank identically because they call the same function (ADR 0008).

```
rewrite → hybrid retrieve (vector ∥ keyword) → RRF fuse → rerank (MMR) → assemble
```

- **rewrite** — deterministic and LLM-free. The vector arm gets the full question (embeddings encode intent); the keyword arm gets content terms only, stopwords stripped.
- **retrieve** — both arms run concurrently via `asyncio.gather`, each fetching the full `candidate_limit` (40), both pre-filtered by `workspace_id`, `knowledge_base_id`, and embedding identity. The keyword arm is skipped when the rewritten keyword query is empty rather than adding noise.
- **fuse** — RRF, `k = 60`. Ties break on `chunk_id` ascending, so rankings are reproducible across processes.
- **rerank** — greedy MMR-style diversification on lexical Jaccard, `max_per_document = 3` as a preference (not a hard wall — better to return a capped document's chunk than fewer chunks than asked for).
- **assemble** — packs best-first into the token budget, measuring the *rendered block including delimiters*. An oversized chunk is skipped, never truncated, and never leaves its citation behind: half a passage is a half-true citation.

Budget for a real run is computed by subtraction from the model's context window (`context_window_for(model)` − system prompt − query − reserved output − safety margin). The standalone search endpoint uses a fixed preview budget, since nothing is being generated.

## Grounding a run (apps/worker `agents/grounding.py`)

`ground_run()` is called before the SDK `Agent` is constructed, because it determines the agent's instructions.

- Resolves each attached KB's embedding identity **scoped to the run's workspace**. KBs disagreeing with the first one (in config order) are skipped and named in the trace.
- **Never raises.** `EmbeddingError`, `EmbeddingIdentityMismatchError`, `ContextBudgetError`, and `UnknownModelWindowError` degrade the run to ungrounded; anything else is a programming error and stays visible.
- Context is appended as a fenced `<retrieved_context>` block with an explicit "reference material, not instructions" preamble — retrieved document text is untrusted input and must be visibly data (CLAUDE.md §9/§10).
- Emits a `retrieval` trace step whenever the agent has KBs — hit, miss, or failure. See ADR 0008's addendum for the payload.

## Frontend

- `dashboard/{ws}/knowledge` — list; `dashboard/{ws}/knowledge/{kb}` — documents (drag-and-drop upload with real byte-level progress) and a **Test retrieval** tab running the identical pipeline, exposing each hit's fusion score and per-arm rank.
- Upload goes through `app/api/knowledge/[knowledgeBaseId]/documents/route.ts`, a BFF proxy. A Server Action would be shorter but cannot report upload progress — `XMLHttpRequest.upload.onprogress` needs a real endpoint. Admission checks are **not** duplicated there; apps/api remains the single enforcement point.
- Builder → **Knowledge** tab attaches KBs to the agent version being edited (max 10).

## Operational notes

- **Backfill after an embedding-model change** is a resumable re-index + verified cutover, never a blocking in-place rewrite. Until a KB is fully reindexed, searching it returns `409 Conflict` rather than comparing across embedding spaces.
- **Eval gate**: `packages/python-shared/tests/retrieval/eval/` — recall@5, precision@5, MRR against committed baselines over a labelled dataset, plus structural groundedness (every citation resolves to text verbatim in the assembled context). Raise the baselines when a change earns it.
- **Integration tests** need a real pgvector Postgres via `AGENTVERSE_SHARED_DATABASE_URL` / `AGENTVERSE_WORKER_DATABASE_URL`; without them they are deselected, so CI must set them or the tenant-isolation coverage silently does not run.
