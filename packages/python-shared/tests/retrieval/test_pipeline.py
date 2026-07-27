from __future__ import annotations

import pytest

from agentverse_shared.retrieval.pipeline import (
    EmbeddingIdentityMismatchError,
    RetrievalConfig,
    retrieve_context,
)
from tests.retrieval.conftest import FakeEmbedder, FakeSearch, WordCounter, chunk

MODEL = "text-embedding-3-small"
VERSION = "1"


async def _run(search: FakeSearch, embedder: FakeEmbedder, **overrides: object) -> object:
    kwargs: dict[str, object] = {
        "query": "how do I cancel my subscription",
        "workspace_id": "ws-1",
        "knowledge_base_ids": ["kb-1"],
        "embedding_model": MODEL,
        "embedding_model_version": VERSION,
        "budget_tokens": 200,
        "search": search,
        "embedder": embedder,
        "counter": WordCounter(),
    }
    kwargs.update(overrides)
    return await retrieve_context(**kwargs)  # type: ignore[arg-type]


async def test_end_to_end_produces_cited_context() -> None:
    search = FakeSearch(
        vector_hits=[chunk("c1", content="cancel from billing settings")],
        keyword_hits=[chunk("c2", content="subscriptions renew monthly", document_id="doc-2")],
    )

    result = await _run(search, FakeEmbedder())

    assert "cancel from billing settings" in result.context_text  # type: ignore[attr-defined]
    assert {c.chunk_id for c in result.citations} == {"c1", "c2"}  # type: ignore[attr-defined]


async def test_the_query_is_embedded_after_normalization() -> None:
    embedder = FakeEmbedder()
    await _run(FakeSearch(), embedder, query="  how   do I cancel ")
    assert embedder.calls == [["how do I cancel"]]


async def test_tenant_and_embedding_identity_reach_the_storage_port() -> None:
    """Rule 11 in practice — the pipeline never resolves workspace_id
    itself, it threads the caller's authenticated value straight through.
    """
    search = FakeSearch(vector_hits=[chunk("c1")], keyword_hits=[chunk("c1")])

    await _run(search, FakeEmbedder())

    call = search.vector_calls[0]
    assert call["workspace_id"] == "ws-1"
    assert call["embedding_model"] == MODEL
    assert call["embedding_model_version"] == VERSION


async def test_an_embedder_producing_a_different_model_fails_loudly() -> None:
    """Mixing embedding-model versions in one similarity search raises no
    error at the database — results just quietly get worse. The mismatch
    has to be caught here or not at all.
    """
    with pytest.raises(EmbeddingIdentityMismatchError):
        await _run(FakeSearch(), FakeEmbedder(model_name="text-embedding-3-large"))


async def test_a_version_bump_alone_also_fails_loudly() -> None:
    with pytest.raises(EmbeddingIdentityMismatchError):
        await _run(FakeSearch(), FakeEmbedder(version="2"))


async def test_no_knowledge_bases_short_circuits_before_spending_on_an_embedding() -> None:
    embedder = FakeEmbedder()
    result = await _run(FakeSearch(), embedder, knowledge_base_ids=[])
    assert result.context_text == ""  # type: ignore[attr-defined]
    assert embedder.calls == []


async def test_a_blank_query_short_circuits() -> None:
    embedder = FakeEmbedder()
    result = await _run(FakeSearch(), embedder, query="   ")
    assert result.citations == []  # type: ignore[attr-defined]
    assert embedder.calls == []


async def test_config_caps_the_number_of_chunks_offered_to_assembly() -> None:
    search = FakeSearch(
        vector_hits=[
            chunk(f"c{i}", content=f"distinct passage {i}", document_id=f"doc-{i}")
            for i in range(10)
        ]
    )

    result = await _run(search, FakeEmbedder(), config=RetrievalConfig(top_k=3))

    assert len(result.citations) <= 3  # type: ignore[attr-defined]


async def test_assembly_respects_the_budget_end_to_end() -> None:
    search = FakeSearch(
        vector_hits=[
            chunk(f"c{i}", content="word " * 20, document_id=f"doc-{i}") for i in range(10)
        ]
    )

    result = await _run(search, FakeEmbedder(), budget_tokens=40)

    assert result.used_tokens <= 40  # type: ignore[attr-defined]
