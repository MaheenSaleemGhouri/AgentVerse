"""Route-level tests for the knowledge-base API.

Every dependency that would touch I/O — the repository, the document
store, the embedding provider, the chunk search — is overridden with a
fake (CLAUDE.md §11). What is being tested here is the *route's* own
behaviour: status codes, tenancy resolution, and admission rejection.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from agentverse_shared.embeddings.port import EmbeddingResult, EmbeddingUnavailableError
from agentverse_shared.retrieval.types import RetrievedChunk
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient

from agentverse_api.auth_service.domain.entities import WorkspaceContext, WorkspaceSettings
from agentverse_api.auth_service.domain.role import Role
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_member,
    require_viewer,
)
from agentverse_api.auth_service.interface.dependencies.services import (
    get_workspace_settings_service,
)
from agentverse_api.main import create_app
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_chunk_search,
    get_document_store,
    get_embedding_provider,
    get_job_queue_producer,
    get_knowledge_repository,
    get_token_counter,
)
from tests.fakes.knowledge_repository import FakeKnowledgeRepository

WORKSPACE_ID = "ws-1"
OTHER_WORKSPACE_ID = "ws-2"
STREAM = "queue:jobs"
BASE = f"/api/v1/workspaces/{WORKSPACE_ID}/knowledge-bases"


class FakeDocumentStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes) -> None:
        self.objects[key] = data

    async def get(self, key: str) -> bytes:
        return self.objects[key]

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)


class FakeEmbedder:
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if self._error is not None:
            raise self._error
        return EmbeddingResult(
            vectors=[[0.1, 0.2, 0.3] for _ in texts],
            model="text-embedding-3-small",
            model_version="1",
            prompt_tokens=len(texts),
        )

    @property
    def model(self) -> str:
        return "text-embedding-3-small"

    @property
    def model_version(self) -> str:
        return "1"


class FakeChunkSearch:
    def __init__(self, chunks: list[RetrievedChunk] | None = None) -> None:
        self._chunks = chunks or []
        self.calls: list[dict[str, Any]] = []

    async def vector_search(self, **kwargs: Any) -> list[RetrievedChunk]:
        self.calls.append({"arm": "vector", **kwargs})
        return list(self._chunks)

    async def keyword_search(self, **kwargs: Any) -> list[RetrievedChunk]:
        self.calls.append({"arm": "keyword", **kwargs})
        return list(self._chunks)


class FakeWorkspaceSettingsService:
    """Only the one method the upload path calls."""

    def __init__(self, *, storage_limit_mb: int | None) -> None:
        self.storage_limit_mb = storage_limit_mb

    async def get_settings(self, workspace_id: str) -> WorkspaceSettings | None:
        if self.storage_limit_mb is None:
            return None
        return WorkspaceSettings(
            workspace_id=workspace_id,
            logo_url=None,
            brand_color=None,
            custom_domain=None,
            retention_days=None,
            storage_limit_mb=self.storage_limit_mb,
            updated_at=datetime.now(UTC),
            updated_by_user_id=None,
        )


class WordCounter:
    def count(self, text: str) -> int:
        return len(text.split())


@pytest.fixture
async def harness(fake_redis: FakeRedis) -> AsyncIterator[dict[str, Any]]:
    app = create_app()
    repo = FakeKnowledgeRepository()
    store = FakeDocumentStore()
    search = FakeChunkSearch()
    embedder = FakeEmbedder()
    context = WorkspaceContext(workspace_id=WORKSPACE_ID, user_id="user-1", role=Role.MEMBER)

    app.dependency_overrides[require_member] = lambda: context
    app.dependency_overrides[require_viewer] = lambda: context
    app.dependency_overrides[get_knowledge_repository] = lambda: repo
    app.dependency_overrides[get_document_store] = lambda: store
    app.dependency_overrides[get_chunk_search] = lambda: search
    app.dependency_overrides[get_embedding_provider] = lambda: embedder
    app.dependency_overrides[get_token_counter] = lambda: WordCounter()
    app.dependency_overrides[get_job_queue_producer] = lambda: JobQueueProducer(
        fake_redis, stream=STREAM
    )
    # Upload admission now consults the workspace's storage policy
    # (owned by auth_service). Defaults to "no limit configured", which
    # is what every workspace that has never opened settings looks like;
    # the quota path itself is covered by `test_upload_quota.py`.
    settings_service = FakeWorkspaceSettingsService(storage_limit_mb=None)
    app.dependency_overrides[get_workspace_settings_service] = lambda: settings_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield {
            "client": client,
            "repo": repo,
            "store": store,
            "search": search,
            "app": app,
        }


async def _create_kb(client: AsyncClient, name: str = "Billing Docs") -> str:
    response = await client.post(BASE, json={"name": name})
    assert response.status_code == 201
    kb_id: str = response.json()["id"]
    return kb_id


async def test_create_knowledge_base_pins_embedding_identity(harness: dict) -> None:
    response = await harness["client"].post(BASE, json={"name": "Billing Docs"})

    assert response.status_code == 201
    body = response.json()
    assert body["workspace_id"] == WORKSPACE_ID
    # Pinned at creation, so a later platform default change cannot
    # reinterpret this KB's existing vectors.
    assert body["embedding_model"]
    assert body["embedding_model_version"]


async def test_knowledge_base_from_another_workspace_returns_404_not_403(
    harness: dict,
) -> None:
    repo: FakeKnowledgeRepository = harness["repo"]
    foreign = await repo.create_knowledge_base(
        workspace_id=OTHER_WORKSPACE_ID,
        name="Someone else's docs",
        description=None,
        embedding_model="text-embedding-3-small",
        embedding_model_version="1",
        created_by_user_id="user-9",
    )

    response = await harness["client"].get(f"{BASE}/{foreign.id}")

    # 404, not 403: a 403 would confirm the resource exists, which leaks
    # another tenant's data by inference (CLAUDE.md §10).
    assert response.status_code == 404


async def test_upload_returns_202_and_enqueues_ingestion(harness: dict) -> None:
    client: AsyncClient = harness["client"]
    kb_id = await _create_kb(client)

    response = await client.post(
        f"{BASE}/{kb_id}/documents",
        files={"file": ("policy.md", b"# Refund policy\n\nRefunds within 30 days.", "text/plain")},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["document"]["status"] == "pending"
    assert body["job_id"]
    assert body["document"]["content_type"] == "text/markdown"
    # The client-supplied filename is recorded for display but never
    # becomes the storage path.
    assert body["document"]["original_filename"] == "policy.md"
    stored_keys = list(harness["store"].objects)
    assert stored_keys and "policy.md" not in stored_keys[0]


async def test_upload_rejects_a_binary_the_client_declared_as_text(harness: dict) -> None:
    client: AsyncClient = harness["client"]
    kb_id = await _create_kb(client)

    response = await client.post(
        f"{BASE}/{kb_id}/documents",
        # Declared text/plain; actually a PNG. The declared type is not
        # an input — content sniffing decides.
        files={"file": ("notes.txt", b"\x89PNG\r\n\x1a\n\x00binary", "text/plain")},
    )

    assert response.status_code == 422
    assert "PNG" in response.json()["detail"]
    assert harness["store"].objects == {}


async def test_upload_rejects_an_empty_file(harness: dict) -> None:
    client: AsyncClient = harness["client"]
    kb_id = await _create_kb(client)

    response = await client.post(
        f"{BASE}/{kb_id}/documents", files={"file": ("empty.txt", b"", "text/plain")}
    )

    assert response.status_code == 422


async def test_upload_to_unknown_knowledge_base_returns_404(harness: dict) -> None:
    response = await harness["client"].post(
        f"{BASE}/00000000-0000-0000-0000-000000000000/documents",
        files={"file": ("a.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 404


async def test_reindex_clears_content_hash_and_requeues(harness: dict) -> None:
    client: AsyncClient = harness["client"]
    repo: FakeKnowledgeRepository = harness["repo"]
    kb_id = await _create_kb(client)
    upload = await client.post(
        f"{BASE}/{kb_id}/documents", files={"file": ("a.txt", b"hello there", "text/plain")}
    )
    document_id = upload.json()["document"]["id"]
    # Simulate a completed ingestion so the reset has something to undo.
    from dataclasses import replace

    from agentverse_api.orchestration_service.domain.knowledge_entities import DocumentStatus

    repo.documents[document_id] = replace(
        repo.documents[document_id],
        status=DocumentStatus.INDEXED,
        content_hash="abc123",
        chunk_count=4,
    )

    response = await client.post(f"{BASE}/{kb_id}/documents/{document_id}/reindex")

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    # The hash must be cleared, not merely the status: ingestion
    # short-circuits on an unchanged hash, so leaving it would make
    # "reindex" a no-op.
    assert repo.documents[document_id].content_hash == ""


async def test_reindex_of_unknown_document_returns_404(harness: dict) -> None:
    client: AsyncClient = harness["client"]
    kb_id = await _create_kb(client)

    response = await client.post(
        f"{BASE}/{kb_id}/documents/00000000-0000-0000-0000-000000000000/reindex"
    )

    assert response.status_code == 404


async def test_delete_knowledge_base_cascades_to_its_documents(harness: dict) -> None:
    client: AsyncClient = harness["client"]
    kb_id = await _create_kb(client)
    await client.post(
        f"{BASE}/{kb_id}/documents", files={"file": ("a.txt", b"hello there", "text/plain")}
    )

    assert (await client.delete(f"{BASE}/{kb_id}")).status_code == 204
    assert (await client.get(f"{BASE}/{kb_id}")).status_code == 404
    assert (await client.get(f"{BASE}/{kb_id}/documents")).status_code == 404


async def test_search_is_scoped_to_the_authenticated_workspace(harness: dict) -> None:
    client: AsyncClient = harness["client"]
    search: FakeChunkSearch = harness["search"]
    kb_id = await _create_kb(client)
    search._chunks = [
        RetrievedChunk(
            chunk_id="chunk-1",
            kb_document_id="doc-1",
            knowledge_base_id=kb_id,
            workspace_id=WORKSPACE_ID,
            chunk_index=0,
            content="Refunds are issued within 30 days.",
            token_count=6,
            score=0.9,
        )
    ]

    response = await client.post(f"{BASE}/{kb_id}/search", json={"query": "refund window"})

    assert response.status_code == 200
    body = response.json()
    assert [h["chunk_id"] for h in body["hits"]] == ["chunk-1"]
    assert [c["chunk_id"] for c in body["citations"]] == ["chunk-1"]
    # Asserted on the arguments the port received — a query that forgot
    # the tenant filter would still look right against a fake that
    # filters on the caller's behalf (Rule 11).
    assert search.calls
    for call in search.calls:
        assert call["workspace_id"] == WORKSPACE_ID
        assert call["knowledge_base_ids"] == [kb_id]


async def test_search_threads_the_knowledge_bases_own_embedding_identity_to_storage(
    harness: dict,
) -> None:
    client: AsyncClient = harness["client"]
    search: FakeChunkSearch = harness["search"]
    kb_id = await _create_kb(client)

    assert (
        await client.post(f"{BASE}/{kb_id}/search", json={"query": "refund window"})
    ).status_code == 200

    # Both arms filter on the identity so they draw from exactly the same
    # candidate pool — fusing two differently-scoped pools would produce
    # meaningless ranks with no error.
    assert search.calls
    for call in search.calls:
        assert call["embedding_model"] == "text-embedding-3-small"
        assert call["embedding_model_version"] == "1"


async def test_search_on_a_knowledge_base_indexed_by_another_model_returns_409(
    harness: dict,
) -> None:
    client: AsyncClient = harness["client"]
    repo: FakeKnowledgeRepository = harness["repo"]
    kb = await repo.create_knowledge_base(
        workspace_id=WORKSPACE_ID,
        name="Legacy KB",
        description=None,
        # Embedded under an identity this deployment no longer produces.
        embedding_model="text-embedding-3-small",
        embedding_model_version="0",
        created_by_user_id="user-1",
    )

    response = await client.post(f"{BASE}/{kb.id}/search", json={"query": "anything"})

    # Searching anyway would compare vectors from two different spaces
    # and silently return plausible nonsense — a conflict the user
    # resolves by reindexing, not a server bug.
    assert response.status_code == 409
    assert "Reindex" in response.json()["detail"]


async def test_search_rejects_an_empty_query(harness: dict) -> None:
    client: AsyncClient = harness["client"]
    kb_id = await _create_kb(client)

    response = await client.post(f"{BASE}/{kb_id}/search", json={"query": ""})

    assert response.status_code == 422


async def test_embedding_provider_outage_returns_503_without_leaking_the_provider_error(
    harness: dict,
) -> None:
    client: AsyncClient = harness["client"]
    kb_id = await _create_kb(client)
    harness["app"].dependency_overrides[get_embedding_provider] = lambda: FakeEmbedder(
        error=EmbeddingUnavailableError("openai.APIConnectionError: connection refused")
    )

    response = await client.post(f"{BASE}/{kb_id}/search", json={"query": "refund window"})

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "openai" not in detail.lower()
    assert "connection refused" not in detail
