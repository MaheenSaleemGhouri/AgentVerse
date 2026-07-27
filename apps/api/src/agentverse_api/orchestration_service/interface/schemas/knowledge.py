"""Request/response models for the knowledge-base API.

Every free-text field is length-capped (CLAUDE.md §7): `query` reaches an
embedding call, so an uncapped field is both a cost vector and the outer
bound on prompt-injection payload size.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateKnowledgeBaseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class KnowledgeBaseResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str | None
    embedding_model: str
    embedding_model_version: str
    created_at: datetime
    updated_at: datetime


class KbDocumentResponse(BaseModel):
    id: str
    knowledge_base_id: str
    original_filename: str
    content_type: str
    size_bytes: int
    status: str
    error_message: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class UploadDocumentResponse(BaseModel):
    """202 body. The document is durable and queued; it is not searchable
    until ingestion moves it to `indexed`, which the client polls for.
    """

    document: KbDocumentResponse
    job_id: str


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=25)


class CitationResponse(BaseModel):
    chunk_id: str
    kb_document_id: str
    knowledge_base_id: str
    chunk_index: int


class SearchHitResponse(BaseModel):
    chunk_id: str
    kb_document_id: str
    chunk_index: int
    content: str
    #: Fusion score plus each arm's contribution — surfaced rather than
    #: hidden so "why did this chunk surface?" is answerable from the API
    #: alone, which is what makes this endpoint a usable debugging tool.
    score: float
    vector_rank: int | None
    keyword_rank: int | None


class SearchResponse(BaseModel):
    hits: list[SearchHitResponse]
    citations: list[CitationResponse]
    context_text: str
    used_tokens: int
    budget_tokens: int
    dropped_chunk_count: int
