"""Ingestion job tests against in-memory fakes — no Postgres, no network,
no real embedding spend (CLAUDE.md §11).

Covers the two acceptance criteria this job owns from docs/roadmap.md
Phase 5: idempotent re-ingestion on unchanged content, and refusal to
write vectors whose embedding model disagrees with the knowledge base.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import pytest
from agentverse_shared.embeddings.port import EmbeddingError, EmbeddingResult
from agentverse_shared.storage.document_store import DocumentNotFoundError

from agentverse_worker.jobs.kb_ingest_job import handle_kb_ingest_job
from agentverse_worker.knowledge.repository import (
    ChunkRow,
    DocumentRecord,
    KnowledgeBaseRecord,
)
from agentverse_worker.queue.models import Job

DIM = 4
WS = "11111111-1111-1111-1111-111111111111"
OTHER_WS = "22222222-2222-2222-2222-222222222222"
KB_ID = "33333333-3333-3333-3333-333333333333"
DOC_ID = "44444444-4444-4444-4444-444444444444"
KEY = f"{WS}/55555555-5555-5555-5555-555555555555.txt"


class WordCounter:
    def count(self, text: str) -> int:
        return len(text.split())


@dataclass
class FakeRepo:
    document: DocumentRecord | None
    knowledge_base: KnowledgeBaseRecord | None
    chunks: list[ChunkRow] = field(default_factory=list)
    status: str = "pending"
    error_message: str | None = None
    indexed_chunk_count: int | None = None
    deleted_calls: int = 0

    async def get_document(self, document_id: str) -> DocumentRecord | None:
        return self.document

    async def get_knowledge_base(self, kb_id: str) -> KnowledgeBaseRecord | None:
        return self.knowledge_base

    async def mark_processing(self, document_id: str) -> None:
        self.status = "processing"

    async def mark_indexed(self, *, document_id: str, chunk_count: int, content_hash: str) -> None:
        self.status = "indexed"
        self.indexed_chunk_count = chunk_count

    async def mark_failed(self, *, document_id: str, error_message: str) -> None:
        self.status = "failed"
        self.error_message = error_message

    async def count_chunks_for_hash(self, *, document_id: str, content_hash: str) -> int:
        return len([c for c in self.chunks if c.content_hash == content_hash])

    async def delete_chunks(self, document_id: str) -> None:
        self.deleted_calls += 1
        self.chunks = []

    async def insert_chunks(self, chunks: list[ChunkRow]) -> int:
        self.chunks.extend(chunks)
        return len(chunks)


@dataclass
class FakeStore:
    data: bytes = b""
    raise_missing: bool = False

    async def put(self, key: str, data: bytes) -> None:
        self.data = data

    async def get(self, key: str) -> bytes:
        if self.raise_missing:
            raise DocumentNotFoundError(key)
        return self.data

    async def delete(self, key: str) -> None:
        self.data = b""


@dataclass
class FakeEmbedder:
    model: str = "text-embedding-3-small"
    model_version: str = "1"
    dimensions: int = DIM
    raise_error: Exception | None = None
    calls: list[list[str]] = field(default_factory=list)

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if self.raise_error is not None:
            raise self.raise_error
        self.calls.append(list(texts))
        return EmbeddingResult(
            vectors=[[float(i)] * DIM for i in range(len(texts))],
            model=self.model,
            model_version=self.model_version,
            prompt_tokens=len(texts),
        )


def _document(**overrides: object) -> DocumentRecord:
    base = DocumentRecord(
        id=DOC_ID,
        workspace_id=WS,
        knowledge_base_id=KB_ID,
        storage_key=KEY,
        original_filename="notes.txt",
        content_type="text/plain",
        status="pending",
        content_hash="",
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def _kb(**overrides: object) -> KnowledgeBaseRecord:
    base = KnowledgeBaseRecord(
        id=KB_ID,
        workspace_id=WS,
        embedding_model="text-embedding-3-small",
        embedding_model_version="1",
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def _job(document_id: str | None = DOC_ID) -> Job:
    payload = {} if document_id is None else {"kb_document_id": document_id}
    return Job(job_id="j1", job_type="kb_ingest", payload=payload, attempt=1, max_attempts=3)


async def _run(repo: FakeRepo, store: FakeStore, embedder: FakeEmbedder, job: Job | None = None):
    return await handle_kb_ingest_job(
        job or _job(), repo=repo, store=store, embedder=embedder, counter=WordCounter()
    )


# --- happy path ---------------------------------------------------------


async def test_indexes_a_document_into_chunks() -> None:
    repo = FakeRepo(document=_document(), knowledge_base=_kb())
    store = FakeStore(data=b"First paragraph here.\n\nSecond paragraph here.")

    result = await _run(repo, store, FakeEmbedder())

    assert result.output is not None
    assert result.output["status"] == "indexed"
    assert repo.status == "indexed"
    assert len(repo.chunks) >= 1


async def test_chunks_carry_workspace_id_for_tenant_isolation() -> None:
    # Retrieval pre-filters on this column; a chunk written without it
    # (or with the wrong one) is a cross-tenant leak (CLAUDE.md Rule 11).
    repo = FakeRepo(document=_document(), knowledge_base=_kb())

    await _run(repo, FakeStore(data=b"Some content here."), FakeEmbedder())

    assert repo.chunks
    assert all(c.workspace_id == WS for c in repo.chunks)
    assert all(c.knowledge_base_id == KB_ID for c in repo.chunks)


async def test_chunks_record_the_embedding_model_and_version() -> None:
    # Without these, a later similarity search cannot exclude vectors from
    # a different model and scores become meaningless.
    repo = FakeRepo(document=_document(), knowledge_base=_kb())

    await _run(repo, FakeStore(data=b"Content."), FakeEmbedder())

    assert all(c.embedding_model == "text-embedding-3-small" for c in repo.chunks)
    assert all(c.embedding_model_version == "1" for c in repo.chunks)


async def test_every_chunk_gets_its_own_vector_in_order() -> None:
    repo = FakeRepo(document=_document(), knowledge_base=_kb())
    text = b"\n\n".join(f"Paragraph number {i} content".encode() for i in range(5))

    await _run(repo, FakeStore(data=text), FakeEmbedder())

    ordered = sorted(repo.chunks, key=lambda c: c.chunk_index)
    assert [c.embedding[0] for c in ordered] == [float(i) for i in range(len(ordered))]


# --- idempotency (roadmap acceptance criterion) -------------------------


async def test_re_ingesting_unchanged_content_creates_no_duplicate_chunks() -> None:
    repo = FakeRepo(document=_document(), knowledge_base=_kb())
    store = FakeStore(data=b"Stable content that will not change.")

    await _run(repo, store, FakeEmbedder())
    first_count = len(repo.chunks)

    await _run(repo, store, FakeEmbedder())

    assert len(repo.chunks) == first_count
    assert repo.status == "indexed"


async def test_re_ingesting_unchanged_content_spends_no_embedding_budget() -> None:
    repo = FakeRepo(document=_document(), knowledge_base=_kb())
    store = FakeStore(data=b"Stable content.")
    await _run(repo, store, FakeEmbedder())

    second_embedder = FakeEmbedder()
    await _run(repo, store, second_embedder)

    # The short-circuit exists specifically to avoid re-paying for
    # embeddings on an at-least-once redelivery.
    assert second_embedder.calls == []


async def test_changed_content_replaces_the_old_chunks() -> None:
    repo = FakeRepo(document=_document(), knowledge_base=_kb())
    await _run(repo, FakeStore(data=b"Original content here."), FakeEmbedder())

    await _run(repo, FakeStore(data=b"Completely different content now."), FakeEmbedder())

    # Stale chunks describe text that no longer exists; leaving them would
    # let retrieval cite a version of the document that is gone.
    assert repo.deleted_calls >= 1
    assert all("Original" not in c.content for c in repo.chunks)


# --- embedding-model mismatch ------------------------------------------


async def test_refuses_to_index_when_the_kb_expects_a_different_model() -> None:
    repo = FakeRepo(
        document=_document(), knowledge_base=_kb(embedding_model="text-embedding-3-large")
    )

    result = await _run(repo, FakeStore(data=b"Content."), FakeEmbedder())

    assert repo.status == "failed"
    assert repo.chunks == []
    assert result.output is not None and result.output["status"] == "failed"
    assert repo.error_message is not None and "backfill" in repo.error_message


async def test_refuses_to_index_when_only_the_model_version_differs() -> None:
    # A provider-side model refresh under the same name still produces
    # incomparable vectors — the version guard is not redundant.
    repo = FakeRepo(document=_document(), knowledge_base=_kb(embedding_model_version="2"))

    await _run(repo, FakeStore(data=b"Content."), FakeEmbedder())

    assert repo.status == "failed"
    assert repo.chunks == []


# --- tenancy ------------------------------------------------------------


async def test_refuses_when_document_and_kb_belong_to_different_workspaces() -> None:
    # Indexing here would write chunks under the wrong tenant.
    repo = FakeRepo(document=_document(), knowledge_base=_kb(workspace_id=OTHER_WS))

    await _run(repo, FakeStore(data=b"Content."), FakeEmbedder())

    assert repo.status == "failed"
    assert repo.chunks == []
    assert repo.error_message is not None and "workspace mismatch" in repo.error_message


# --- failure handling ---------------------------------------------------


async def test_missing_document_is_skipped_not_failed() -> None:
    # Soft-deleted between enqueue and pickup: nothing to do, nothing wrong.
    repo = FakeRepo(document=None, knowledge_base=_kb())

    result = await _run(repo, FakeStore(), FakeEmbedder())

    assert result.output is not None and result.output["status"] == "skipped"


async def test_missing_payload_field_fails_the_job() -> None:
    repo = FakeRepo(document=_document(), knowledge_base=_kb())

    result = await _run(repo, FakeStore(), FakeEmbedder(), job=_job(document_id=None))

    assert result.error is not None


async def test_missing_stored_file_marks_the_document_failed() -> None:
    repo = FakeRepo(document=_document(), knowledge_base=_kb())

    await _run(repo, FakeStore(raise_missing=True), FakeEmbedder())

    assert repo.status == "failed"
    assert repo.error_message is not None and "unavailable" in repo.error_message


async def test_unreadable_content_marks_the_document_failed() -> None:
    repo = FakeRepo(document=_document(), knowledge_base=_kb())

    # Invalid UTF-8 — extraction refuses rather than embedding mojibake.
    await _run(repo, FakeStore(data=b"\xff\xfe\x00bad"), FakeEmbedder())

    assert repo.status == "failed"
    assert repo.chunks == []


async def test_embedding_failure_marks_the_document_failed_without_partial_chunks() -> None:
    repo = FakeRepo(document=_document(), knowledge_base=_kb())
    embedder = FakeEmbedder(raise_error=EmbeddingError("provider exploded"))

    await _run(repo, FakeStore(data=b"Content here."), embedder)

    assert repo.status == "failed"
    # A half-embedded document must not leave orphan chunks behind.
    assert repo.chunks == []


async def test_empty_file_marks_the_document_failed() -> None:
    repo = FakeRepo(document=_document(), knowledge_base=_kb())

    await _run(repo, FakeStore(data=b"   \n\n  "), FakeEmbedder())

    assert repo.status == "failed"


async def test_worker_does_not_crash_on_an_unexpected_error() -> None:
    # The queue would otherwise retry to the DLQ on a bug that will
    # reproduce identically every time.
    repo = FakeRepo(document=_document(), knowledge_base=_kb())
    embedder = FakeEmbedder(raise_error=RuntimeError("boom"))

    result = await _run(repo, FakeStore(data=b"Content."), embedder)

    assert result.output is not None and result.output["status"] == "failed"
    assert repo.status == "failed"


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("notes.md", b"# Heading\n\nBody text here."),
        ("data.csv", b"name,value\nalpha,1\nbeta,2"),
        ("code.py", b"def alpha():\n    return 1\n"),
        ("plain.txt", b"Just some prose content."),
    ],
)
async def test_indexes_each_supported_text_format(filename: str, content: bytes) -> None:
    repo = FakeRepo(document=_document(original_filename=filename), knowledge_base=_kb())

    await _run(repo, FakeStore(data=content), FakeEmbedder())

    assert repo.status == "indexed"
    assert repo.chunks
