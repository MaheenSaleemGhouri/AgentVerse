"""Knowledge-base ingestion: stored bytes → text → chunks → embeddings →
`kb_chunks`.

Runs as a background job (CLAUDE.md Rule 14 — never inline in a request):
extracting a PDF and embedding hundreds of chunks is seconds-to-minutes
of work behind a provider call.

Idempotency (CLAUDE.md Rule 14, `vector-database-expert`) is per
`(kb_document_id, content_hash)` and layered:
1. The job short-circuits if chunks for this exact content already exist.
2. The insert is `ON CONFLICT DO NOTHING` against the DB's unique
   constraint, so a genuine race between two deliveries still cannot
   duplicate a chunk or double-spend embedding budget.
"""

from __future__ import annotations

import hashlib
import logging
import uuid

from agentverse_shared.embeddings.openai_provider import embed_in_batches
from agentverse_shared.embeddings.port import EmbeddingError, EmbeddingProvider
from agentverse_shared.storage.document_store import DocumentStore, DocumentStoreError
from agentverse_shared.text.chunking import chunk_text, detect_content_kind
from agentverse_shared.text.tokenizer import TokenCounter

from agentverse_worker.knowledge.extraction import ExtractionError, extract_text
from agentverse_worker.knowledge.repository import (
    ChunkRow,
    DocumentRecord,
    KnowledgeBaseRecord,
    KnowledgeRepositoryProtocol,
)
from agentverse_worker.queue.models import Job, JobResult

logger = logging.getLogger(__name__)

#: Embedding calls per provider request. Below OpenAI's 2048 cap with
#: headroom, and small enough that one transient failure re-costs little.
_EMBED_BATCH_SIZE = 128


class _IngestFailedError(Exception):
    """A user-visible ingestion failure. Recorded on the document as
    `failed` + reason rather than crashing the worker or retrying forever
    — a malformed PDF will be just as malformed on the next attempt.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def handle_kb_ingest_job(
    job: Job,
    *,
    repo: KnowledgeRepositoryProtocol,
    store: DocumentStore,
    embedder: EmbeddingProvider,
    counter: TokenCounter,
) -> JobResult:
    """Payload carries only `kb_document_id`; everything else is read from
    Postgres, so a stale queued payload can never contradict current state
    (same reasoning as Phase 4's `agent_run` job).
    """
    document_id = job.payload.get("kb_document_id")
    if not isinstance(document_id, str) or not document_id:
        return JobResult.fail("kb_ingest job payload missing kb_document_id")

    document = await repo.get_document(document_id)
    if document is None:
        # Soft-deleted or purged between enqueue and pickup. Succeeds
        # rather than fails: there is nothing to do and nothing wrong.
        logger.info("kb_ingest_skipped_missing_document document_id=%s", document_id)
        return JobResult.ok({"kb_document_id": document_id, "status": "skipped"})

    knowledge_base = await repo.get_knowledge_base(document.knowledge_base_id)
    if knowledge_base is None:
        await repo.mark_failed(
            document_id=document_id, error_message="knowledge base no longer exists"
        )
        return JobResult.ok({"kb_document_id": document_id, "status": "failed"})

    # Tenancy cross-check. Both rows carry workspace_id independently;
    # if they disagree, something has gone badly wrong and indexing would
    # write chunks under the wrong tenant (CLAUDE.md Rule 11).
    if document.workspace_id != knowledge_base.workspace_id:
        logger.error(
            "kb_ingest_tenancy_mismatch document_id=%s doc_ws=%s kb_ws=%s",
            document_id,
            document.workspace_id,
            knowledge_base.workspace_id,
        )
        await repo.mark_failed(
            document_id=document_id, error_message="workspace mismatch between document and KB"
        )
        return JobResult.ok({"kb_document_id": document_id, "status": "failed"})

    await repo.mark_processing(document_id)

    try:
        chunk_count = await _ingest(
            document=document,
            knowledge_base=knowledge_base,
            repo=repo,
            store=store,
            embedder=embedder,
            counter=counter,
        )
    except _IngestFailedError as exc:
        logger.warning("kb_ingest_failed document_id=%s reason=%s", document_id, exc.reason)
        await repo.mark_failed(document_id=document_id, error_message=exc.reason)
        return JobResult.ok({"kb_document_id": document_id, "status": "failed"})
    except Exception as exc:  # noqa: BLE001 - recorded on the document, not a worker crash
        logger.exception("kb_ingest_unexpected_error document_id=%s", document_id)
        await repo.mark_failed(document_id=document_id, error_message=f"unexpected error: {exc}")
        return JobResult.ok({"kb_document_id": document_id, "status": "failed"})

    return JobResult.ok(
        {"kb_document_id": document_id, "status": "indexed", "chunk_count": chunk_count}
    )


async def _ingest(
    *,
    document: DocumentRecord,
    knowledge_base: KnowledgeBaseRecord,
    repo: KnowledgeRepositoryProtocol,
    store: DocumentStore,
    embedder: EmbeddingProvider,
    counter: TokenCounter,
) -> int:
    # A knowledge base declares the model every chunk in it must use.
    # Embedding with a different one would put two incomparable vector
    # families in one HNSW index and silently destroy relevance scores —
    # the exact failure `vector-database-expert` flags as never throwing.
    if (
        knowledge_base.embedding_model != embedder.model
        or knowledge_base.embedding_model_version != embedder.model_version
    ):
        raise _IngestFailedError(
            f"knowledge base expects "
            f"{knowledge_base.embedding_model}@{knowledge_base.embedding_model_version} "
            f"but the worker is configured for {embedder.model}@{embedder.model_version} — "
            f"changing model requires a backfill and cutover, not a config swap"
        )

    try:
        data = await store.get(document.storage_key)
    except DocumentStoreError as exc:
        raise _IngestFailedError(f"stored file unavailable: {exc}") from exc

    try:
        extracted = extract_text(
            data,
            filename=document.original_filename,
            declared_content_type=document.content_type,
        )
    except ExtractionError as exc:
        raise _IngestFailedError(str(exc)) from exc

    # Hash the *extracted text*, not the raw bytes: two PDFs differing
    # only in metadata produce identical text, and re-embedding identical
    # text is pure waste.
    content_hash = hashlib.sha256(extracted.text.encode("utf-8")).hexdigest()

    already = await repo.count_chunks_for_hash(document_id=document.id, content_hash=content_hash)
    if already > 0:
        logger.info("kb_ingest_idempotent_skip document_id=%s chunks=%s", document.id, already)
        await repo.mark_indexed(
            document_id=document.id, chunk_count=already, content_hash=content_hash
        )
        return already

    kind = detect_content_kind(document.original_filename, extracted.detected_type)
    chunks = chunk_text(extracted.text, kind=kind, counter=counter)
    if not chunks:
        raise _IngestFailedError("document produced no chunks after extraction")

    try:
        embedded = await embed_in_batches(
            embedder, [c.content for c in chunks], batch_size=_EMBED_BATCH_SIZE
        )
    except EmbeddingError as exc:
        raise _IngestFailedError(f"embedding failed: {exc}") from exc

    rows = [
        ChunkRow(
            id=str(uuid.uuid4()),
            workspace_id=document.workspace_id,
            knowledge_base_id=document.knowledge_base_id,
            kb_document_id=document.id,
            chunk_index=chunk.index,
            content=chunk.content,
            token_count=chunk.token_count,
            embedding=vector,
            embedding_model=embedded.model,
            embedding_model_version=embedded.model_version,
            content_hash=content_hash,
        )
        # strict=True: a length mismatch would silently pair chunks with
        # the wrong vectors, which is far worse than an exception.
        for chunk, vector in zip(chunks, embedded.vectors, strict=True)
    ]

    # Re-index of *changed* content: the old chunks describe text that no
    # longer exists, so they are removed rather than left to pollute
    # retrieval alongside the new ones.
    await repo.delete_chunks(document.id)
    await repo.insert_chunks(rows)
    await repo.mark_indexed(
        document_id=document.id, chunk_count=len(rows), content_hash=content_hash
    )

    logger.info(
        "kb_ingest_indexed document_id=%s chunks=%s kind=%s embed_tokens=%s",
        document.id,
        len(rows),
        kind.value,
        embedded.prompt_tokens,
    )
    return len(rows)
