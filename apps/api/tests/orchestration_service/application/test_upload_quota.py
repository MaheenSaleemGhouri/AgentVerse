"""Storage-quota admission on upload.

`workspace_settings.storage_limit_mb` was storable long before anything
read it — the entity's own docstring said so. These tests pin the
behaviour that closed that gap: the limit is checked *before* bytes are
written, an unset limit means unrestricted, and freeing space by
deleting documents actually frees it.
"""

from __future__ import annotations

import pytest
from tests.fakes.knowledge_repository import FakeKnowledgeRepository

from agentverse_api.orchestration_service.application.upload_document import (
    UploadRejectedError,
    upload_document,
)

WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"
ONE_MB = 1024 * 1024


class FakeDocumentStore:
    def __init__(self) -> None:
        self.written: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes) -> None:
        self.written[key] = data

    async def get(self, key: str) -> bytes:
        return self.written[key]


class FakeProducer:
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    async def enqueue_kb_ingest(self, *, kb_document_id: str) -> tuple[str, str]:
        self.enqueued.append(kb_document_id)
        return f"job-{kb_document_id}", "stream"


async def _kb(repo: FakeKnowledgeRepository) -> str:
    kb = await repo.create_knowledge_base(
        workspace_id=WORKSPACE_ID,
        name="kb",
        description=None,
        embedding_model="text-embedding-3-small",
        embedding_model_version="1",
        created_by_user_id="user-1",
    )
    return kb.id


async def _upload(
    repo: FakeKnowledgeRepository,
    store: FakeDocumentStore,
    producer: FakeProducer,
    *,
    kb_id: str,
    size: int,
    quota_bytes: int | None,
) -> None:
    await upload_document(
        workspace_id=WORKSPACE_ID,
        knowledge_base_id=kb_id,
        filename="notes.txt",
        data=b"a" * size,
        max_bytes=50 * ONE_MB,
        repo=repo,
        store=store,
        producer=producer,
        workspace_quota_bytes=quota_bytes,
    )


async def test_no_configured_limit_means_unrestricted() -> None:
    repo, store, producer = FakeKnowledgeRepository(), FakeDocumentStore(), FakeProducer()
    kb_id = await _kb(repo)

    # Every workspace that has never opened settings looks like this;
    # none of them may be newly blocked by shipping enforcement.
    await _upload(repo, store, producer, kb_id=kb_id, size=5 * ONE_MB, quota_bytes=None)
    await _upload(repo, store, producer, kb_id=kb_id, size=5 * ONE_MB, quota_bytes=None)

    assert len(producer.enqueued) == 2


async def test_an_upload_that_would_exceed_the_quota_is_refused() -> None:
    repo, store, producer = FakeKnowledgeRepository(), FakeDocumentStore(), FakeProducer()
    kb_id = await _kb(repo)
    quota = 10 * ONE_MB

    await _upload(repo, store, producer, kb_id=kb_id, size=8 * ONE_MB, quota_bytes=quota)

    with pytest.raises(UploadRejectedError) as excinfo:
        await _upload(repo, store, producer, kb_id=kb_id, size=4 * ONE_MB, quota_bytes=quota)

    assert "storage limit" in str(excinfo.value)


async def test_a_refused_upload_writes_nothing_and_queues_nothing() -> None:
    """Admission, not cleanup: the quota is checked before any byte is
    stored, so a rejected upload leaves no orphaned file and no job.
    """
    repo, store, producer = FakeKnowledgeRepository(), FakeDocumentStore(), FakeProducer()
    kb_id = await _kb(repo)

    with pytest.raises(UploadRejectedError):
        await _upload(repo, store, producer, kb_id=kb_id, size=2 * ONE_MB, quota_bytes=ONE_MB)

    assert store.written == {}
    assert producer.enqueued == []


async def test_an_upload_that_exactly_fills_the_quota_is_allowed() -> None:
    repo, store, producer = FakeKnowledgeRepository(), FakeDocumentStore(), FakeProducer()
    kb_id = await _kb(repo)

    await _upload(repo, store, producer, kb_id=kb_id, size=ONE_MB, quota_bytes=ONE_MB)

    assert len(producer.enqueued) == 1


async def test_deleting_a_document_frees_its_space() -> None:
    repo, store, producer = FakeKnowledgeRepository(), FakeDocumentStore(), FakeProducer()
    kb_id = await _kb(repo)
    quota = 2 * ONE_MB

    await _upload(repo, store, producer, kb_id=kb_id, size=2 * ONE_MB, quota_bytes=quota)
    with pytest.raises(UploadRejectedError):
        await _upload(repo, store, producer, kb_id=kb_id, size=ONE_MB, quota_bytes=quota)

    stored = next(iter(repo.documents.values()))
    await repo.soft_delete_document(workspace_id=WORKSPACE_ID, document_id=stored.id)

    # An admin who deletes a file expects the space back.
    await _upload(repo, store, producer, kb_id=kb_id, size=ONE_MB, quota_bytes=quota)
    assert len(producer.enqueued) == 2


async def test_quota_is_scoped_to_the_workspace() -> None:
    repo, store, producer = FakeKnowledgeRepository(), FakeDocumentStore(), FakeProducer()
    kb_id = await _kb(repo)

    other_kb = await repo.create_knowledge_base(
        workspace_id="22222222-2222-2222-2222-222222222222",
        name="theirs",
        description=None,
        embedding_model="text-embedding-3-small",
        embedding_model_version="1",
        created_by_user_id="user-2",
    )
    await repo.create_document(
        workspace_id="22222222-2222-2222-2222-222222222222",
        knowledge_base_id=other_kb.id,
        storage_key="theirs/big",
        original_filename="big.txt",
        content_type="text/plain",
        size_bytes=100 * ONE_MB,
    )

    # Another tenant's 100 MB must not count against this workspace.
    await _upload(repo, store, producer, kb_id=kb_id, size=ONE_MB, quota_bytes=2 * ONE_MB)
    assert len(producer.enqueued) == 1
