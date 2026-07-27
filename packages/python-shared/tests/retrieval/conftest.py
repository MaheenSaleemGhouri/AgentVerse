"""Fakes shared by the retrieval tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from agentverse_shared.embeddings.port import EmbeddingResult
from agentverse_shared.retrieval.types import RetrievedChunk


def chunk(
    chunk_id: str,
    *,
    content: str = "content",
    document_id: str = "doc-1",
    kb_id: str = "kb-1",
    workspace_id: str = "ws-1",
    index: int = 0,
    tokens: int = 10,
    score: float = 0.9,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        kb_document_id=document_id,
        knowledge_base_id=kb_id,
        workspace_id=workspace_id,
        chunk_index=index,
        content=content,
        token_count=tokens,
        score=score,
    )


class WordCounter:
    """Deterministic `TokenCounter` — one token per whitespace word.

    Lets budget assertions state exact numbers instead of asserting
    against whatever BPE happens to produce, which would make the test
    a restatement of tiktoken rather than of our budgeting logic.
    """

    def count(self, text: str) -> int:
        return len(text.split())


@dataclass
class FakeSearch:
    """In-memory `ChunkSearchPort` that records exactly what it was
    called with, so tenancy/version pre-filtering can be asserted on the
    arguments rather than inferred from results.
    """

    vector_hits: list[RetrievedChunk] = field(default_factory=list)
    keyword_hits: list[RetrievedChunk] = field(default_factory=list)
    vector_calls: list[dict[str, object]] = field(default_factory=list)
    keyword_calls: list[dict[str, object]] = field(default_factory=list)

    async def vector_search(self, **kwargs: object) -> list[RetrievedChunk]:
        self.vector_calls.append(kwargs)
        limit = kwargs["limit"]
        assert isinstance(limit, int)
        return self.vector_hits[:limit]

    async def keyword_search(self, **kwargs: object) -> list[RetrievedChunk]:
        self.keyword_calls.append(kwargs)
        limit = kwargs["limit"]
        assert isinstance(limit, int)
        return self.keyword_hits[:limit]


@dataclass
class FakeEmbedder:
    model_name: str = "text-embedding-3-small"
    version: str = "1"
    vector: list[float] = field(default_factory=lambda: [0.1, 0.2, 0.3])
    calls: list[list[str]] = field(default_factory=list)

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        self.calls.append(texts)
        return EmbeddingResult(
            vectors=[self.vector for _ in texts],
            model=self.model_name,
            model_version=self.version,
            prompt_tokens=len(texts),
        )

    @property
    def model(self) -> str:
        return self.model_name

    @property
    def model_version(self) -> str:
        return self.version

    @property
    def dimensions(self) -> int:
        return len(self.vector)
