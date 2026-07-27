"""`/api/v1/workspaces/{workspace_id}/knowledge-bases` — knowledge-base
CRUD, document upload/reindex, and retrieval preview.

Handlers stay thin (CLAUDE.md §7): resolve dependencies, delegate to an
application-layer function, map the result to a response model. No
chunking, embedding, or retrieval logic lives in this file.

`workspace_id` always comes from `context.workspace_id` — the value the
auth dependency derived from the caller's identity — never from the path
parameter, which is present only to make the URL RESTful (Rule 6).
"""

from __future__ import annotations

from agentverse_shared.embeddings.port import EmbeddingError, EmbeddingProvider
from agentverse_shared.retrieval.pipeline import EmbeddingIdentityMismatchError
from agentverse_shared.retrieval.port import ChunkSearchPort
from agentverse_shared.retrieval.types import AssembledContext
from agentverse_shared.storage.document_store import DocumentStore
from agentverse_shared.text.tokenizer import TokenCounter
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_member,
    require_viewer,
)
from agentverse_api.infrastructure.config import Settings, get_settings
from agentverse_api.orchestration_service.application.search_knowledge import (
    search_knowledge_base,
)
from agentverse_api.orchestration_service.application.upload_document import (
    KnowledgeBaseNotFoundError,
    UploadRejectedError,
    upload_document,
)
from agentverse_api.orchestration_service.domain.knowledge_entities import (
    KbDocument,
    KnowledgeBase,
)
from agentverse_api.orchestration_service.domain.ports.knowledge_repository import (
    KnowledgeRepository,
)
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
from agentverse_api.orchestration_service.interface.schemas.knowledge import (
    CitationResponse,
    CreateKnowledgeBaseRequest,
    KbDocumentResponse,
    KnowledgeBaseResponse,
    SearchHitResponse,
    SearchRequest,
    SearchResponse,
    UploadDocumentResponse,
)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/knowledge-bases", tags=["knowledge-bases"]
)

_KB_NOT_FOUND = "Knowledge base not found"
_DOC_NOT_FOUND = "Document not found"


def _kb_response(kb: KnowledgeBase) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse(
        id=kb.id,
        workspace_id=kb.workspace_id,
        name=kb.name,
        description=kb.description,
        embedding_model=kb.embedding_model,
        embedding_model_version=kb.embedding_model_version,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


def _document_response(document: KbDocument) -> KbDocumentResponse:
    return KbDocumentResponse(
        id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        original_filename=document.original_filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        status=document.status.value,
        error_message=document.error_message,
        chunk_count=document.chunk_count,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.post("", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base_route(
    body: CreateKnowledgeBaseRequest,
    context: WorkspaceContext = Depends(require_member),
    repo: KnowledgeRepository = Depends(get_knowledge_repository),
    settings: Settings = Depends(get_settings),
) -> KnowledgeBaseResponse:
    kb = await repo.create_knowledge_base(
        workspace_id=context.workspace_id,
        name=body.name,
        description=body.description,
        # Pinned at creation time. A later platform default change must
        # not silently reinterpret an existing KB's vectors.
        embedding_model=settings.embedding_model,
        embedding_model_version=settings.embedding_model_version,
        created_by_user_id=context.user_id,
    )
    return _kb_response(kb)


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases_route(
    context: WorkspaceContext = Depends(require_viewer),
    repo: KnowledgeRepository = Depends(get_knowledge_repository),
) -> list[KnowledgeBaseResponse]:
    bases = await repo.list_knowledge_bases(workspace_id=context.workspace_id)
    return [_kb_response(kb) for kb in bases]


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base_route(
    knowledge_base_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    repo: KnowledgeRepository = Depends(get_knowledge_repository),
) -> KnowledgeBaseResponse:
    kb = await repo.get_knowledge_base(
        workspace_id=context.workspace_id, knowledge_base_id=knowledge_base_id
    )
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_KB_NOT_FOUND)
    return _kb_response(kb)


@router.delete("/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_knowledge_base_route(
    knowledge_base_id: str,
    context: WorkspaceContext = Depends(require_member),
    repo: KnowledgeRepository = Depends(get_knowledge_repository),
) -> None:
    deleted = await repo.soft_delete_knowledge_base(
        workspace_id=context.workspace_id, knowledge_base_id=knowledge_base_id
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_KB_NOT_FOUND)


@router.post(
    "/{knowledge_base_id}/documents",
    response_model=UploadDocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document_route(
    knowledge_base_id: str,
    file: UploadFile = File(...),
    context: WorkspaceContext = Depends(require_member),
    repo: KnowledgeRepository = Depends(get_knowledge_repository),
    store: DocumentStore = Depends(get_document_store),
    producer: JobQueueProducer = Depends(get_job_queue_producer),
    settings: Settings = Depends(get_settings),
) -> UploadDocumentResponse:
    """202 — the bytes are durable and ingestion is queued. Chunking and
    embedding are background work (Rule 14), so the client polls the
    document's `status` rather than waiting on this call.
    """
    data = await file.read()
    try:
        result = await upload_document(
            workspace_id=context.workspace_id,
            knowledge_base_id=knowledge_base_id,
            # `UploadFile.filename` is client-controlled; it is recorded
            # for display only and never used to build a storage path.
            filename=file.filename or "document",
            data=data,
            max_bytes=settings.max_document_bytes,
            repo=repo,
            store=store,
            producer=producer,
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_KB_NOT_FOUND) from exc
    except UploadRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return UploadDocumentResponse(
        document=_document_response(result.document), job_id=result.job_id
    )


@router.get("/{knowledge_base_id}/documents", response_model=list[KbDocumentResponse])
async def list_documents_route(
    knowledge_base_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    repo: KnowledgeRepository = Depends(get_knowledge_repository),
) -> list[KbDocumentResponse]:
    kb = await repo.get_knowledge_base(
        workspace_id=context.workspace_id, knowledge_base_id=knowledge_base_id
    )
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_KB_NOT_FOUND)
    documents = await repo.list_documents(
        workspace_id=context.workspace_id, knowledge_base_id=knowledge_base_id
    )
    return [_document_response(d) for d in documents]


@router.delete(
    "/{knowledge_base_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_document_route(
    knowledge_base_id: str,
    document_id: str,
    context: WorkspaceContext = Depends(require_member),
    repo: KnowledgeRepository = Depends(get_knowledge_repository),
) -> None:
    deleted = await repo.soft_delete_document(
        workspace_id=context.workspace_id, document_id=document_id
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_DOC_NOT_FOUND)


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/reindex",
    response_model=KbDocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reindex_document_route(
    knowledge_base_id: str,
    document_id: str,
    context: WorkspaceContext = Depends(require_member),
    repo: KnowledgeRepository = Depends(get_knowledge_repository),
    producer: JobQueueProducer = Depends(get_job_queue_producer),
) -> KbDocumentResponse:
    reset = await repo.reset_document_for_reindex(
        workspace_id=context.workspace_id, document_id=document_id
    )
    if not reset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_DOC_NOT_FOUND)
    await producer.enqueue_kb_ingest(kb_document_id=document_id)

    document = await repo.get_document(workspace_id=context.workspace_id, document_id=document_id)
    if document is None:  # pragma: no cover - reset above proved it exists
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_DOC_NOT_FOUND)
    return _document_response(document)


@router.post("/{knowledge_base_id}/search", response_model=SearchResponse)
async def search_route(
    knowledge_base_id: str,
    body: SearchRequest,
    context: WorkspaceContext = Depends(require_viewer),
    repo: KnowledgeRepository = Depends(get_knowledge_repository),
    search: ChunkSearchPort = Depends(get_chunk_search),
    embedder: EmbeddingProvider = Depends(get_embedding_provider),
    counter: TokenCounter = Depends(get_token_counter),
) -> SearchResponse:
    """Runs the exact pipeline an agent run uses, so what a user sees here
    is what their agent will actually retrieve.
    """
    try:
        assembled = await search_knowledge_base(
            workspace_id=context.workspace_id,
            knowledge_base_id=knowledge_base_id,
            query=body.query,
            top_k=body.top_k,
            repo=repo,
            search=search,
            embedder=embedder,
            counter=counter,
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_KB_NOT_FOUND) from exc
    except EmbeddingIdentityMismatchError as exc:
        # The KB's vectors were written by a model this deployment no
        # longer produces. Searching anyway would compare vectors from
        # two different spaces and return plausible-looking nonsense, so
        # this is a conflict the user must resolve by reindexing — not a
        # 500, which would read as a bug in AgentVerse.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This knowledge base was indexed with a different embedding model. "
                "Reindex its documents before searching."
            ),
        ) from exc
    except EmbeddingError as exc:
        # Translated from the shared taxonomy — a provider exception must
        # never reach the client verbatim (CLAUDE.md §7 error envelope).
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not embed the query — the embedding provider is unavailable.",
        ) from exc

    return _search_response(assembled)


def _search_response(assembled: AssembledContext) -> SearchResponse:
    return SearchResponse(
        hits=[
            SearchHitResponse(
                chunk_id=s.chunk.chunk_id,
                kb_document_id=s.chunk.kb_document_id,
                chunk_index=s.chunk.chunk_index,
                content=s.chunk.content,
                score=s.fused_score,
                vector_rank=s.vector_rank,
                keyword_rank=s.keyword_rank,
            )
            for s in assembled.chunks
        ],
        citations=[
            CitationResponse(
                chunk_id=c.chunk_id,
                kb_document_id=c.kb_document_id,
                knowledge_base_id=c.knowledge_base_id,
                chunk_index=c.chunk_index,
            )
            for c in assembled.citations
        ],
        context_text=assembled.context_text,
        used_tokens=assembled.used_tokens,
        budget_tokens=assembled.budget_tokens,
        dropped_chunk_count=assembled.dropped_chunk_count,
    )
