"""The "test this knowledge base" use case behind `POST .../search`.

Deliberately thin: it resolves the knowledge base's *own* embedding
identity and then calls the same `retrieve_context` pipeline apps/worker
runs during a real agent run. Reimplementing retrieval here would make
this endpoint a debugging surface that lies — showing a user results
their agent will never see (CLAUDE.md Rule 3).
"""

from __future__ import annotations

from agentverse_shared.embeddings.port import EmbeddingProvider
from agentverse_shared.retrieval.pipeline import RetrievalConfig, retrieve_context
from agentverse_shared.retrieval.port import ChunkSearchPort
from agentverse_shared.retrieval.types import AssembledContext
from agentverse_shared.text.tokenizer import TokenCounter

from agentverse_api.orchestration_service.application.upload_document import (
    KnowledgeBaseNotFoundError,
)
from agentverse_api.orchestration_service.domain.ports.knowledge_repository import (
    KnowledgeRepository,
)

#: Budget for the standalone search endpoint. Not a model's real context
#: window — nothing is being generated here, this is a preview of what
#: would be retrieved. A real run computes its budget by subtraction from
#: the target model's window (`assemble.compute_context_budget`).
SEARCH_PREVIEW_BUDGET_TOKENS = 4000


async def search_knowledge_base(
    *,
    workspace_id: str,
    knowledge_base_id: str,
    query: str,
    top_k: int,
    repo: KnowledgeRepository,
    search: ChunkSearchPort,
    embedder: EmbeddingProvider,
    counter: TokenCounter,
) -> AssembledContext:
    kb = await repo.get_knowledge_base(
        workspace_id=workspace_id, knowledge_base_id=knowledge_base_id
    )
    if kb is None:
        raise KnowledgeBaseNotFoundError(knowledge_base_id)

    return await retrieve_context(
        query=query,
        workspace_id=workspace_id,
        knowledge_base_ids=[kb.id],
        # From the knowledge base, never the process default: a KB created
        # under an older embedding model must be searched with that model.
        embedding_model=kb.embedding_model,
        embedding_model_version=kb.embedding_model_version,
        budget_tokens=SEARCH_PREVIEW_BUDGET_TOKENS,
        search=search,
        embedder=embedder,
        counter=counter,
        config=RetrievalConfig(top_k=top_k),
    )
