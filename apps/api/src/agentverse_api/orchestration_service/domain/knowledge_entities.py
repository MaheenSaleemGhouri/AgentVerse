"""Knowledge-base domain entities — plain dataclasses, zero
framework/ORM imports (CLAUDE.md §5).

A knowledge base is a workspace-scoped collection of documents; a
document is chunked into `KbChunk`s, each carrying its own embedding
plus the model/version that produced it. Source content lives in
Postgres — the vector column is the *semantic layer*, never the source
of truth (CLAUDE.md §8; `vector-database-expert`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class EmbeddingModel(StrEnum):
    """The embedding models AgentVerse can produce vectors with.

    A typed constant rather than a string duplicated across ingestion
    and query code paths (`vector-database-expert`'s coding standard) —
    a similarity search must never compare vectors produced by two
    different models, and that invariant is only checkable if the model
    identity is a closed set.
    """

    TEXT_EMBEDDING_3_SMALL = "text-embedding-3-small"


#: Vector dimensionality per embedding model. The `kb_chunks.embedding`
#: column is fixed-width in Postgres, so a model whose dimensionality
#: differs from the column's cannot simply be swapped in — it needs a
#: new column plus a backfill/cutover (see EMBEDDING_MODEL_VERSION).
EMBEDDING_DIMENSIONS: dict[EmbeddingModel, int] = {
    EmbeddingModel.TEXT_EMBEDDING_3_SMALL: 1536,
}

#: The model new ingestion uses. Existing chunks keep whatever model
#: they were written with; retrieval filters by model+version so a
#: mid-backfill knowledge base never mixes versions in one search.
DEFAULT_EMBEDDING_MODEL = EmbeddingModel.TEXT_EMBEDDING_3_SMALL

#: Bumped when the *same* model name would produce different vectors
#: (provider-side model refresh) or when our own pre-embedding text
#: normalization changes. Distinct from the model name so a provider
#: refresh is expressible without inventing a fake model identity.
DEFAULT_EMBEDDING_MODEL_VERSION = "1"


class DocumentStatus(StrEnum):
    """Ingestion lifecycle for one uploaded document.

    `pending` → enqueued, not yet picked up. `processing` → a worker is
    chunking/embedding it. `indexed` → chunks exist and are searchable.
    `failed` → ingestion errored; `error_message` says why.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class KnowledgeBase:
    id: str
    workspace_id: str
    name: str
    description: str | None
    embedding_model: str
    embedding_model_version: str
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class KbDocument:
    id: str
    workspace_id: str
    knowledge_base_id: str
    #: Generated internal storage name — never the client-supplied
    #: filename (CLAUDE.md §10: path-traversal/collision hardening).
    storage_key: str
    original_filename: str
    content_type: str
    size_bytes: int
    #: SHA-256 of the extracted text. Ingestion is idempotent per
    #: `(kb_document_id, content_hash)` — re-uploading unchanged content
    #: must not duplicate chunks or re-spend embedding spend.
    content_hash: str
    status: DocumentStatus
    error_message: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class KbChunk:
    """One retrievable unit. `content` is the source text kept alongside
    the vector so a retrieved chunk is self-explanatory and citable
    without a second lookup (`vector-database-expert`).
    """

    id: str
    workspace_id: str
    knowledge_base_id: str
    kb_document_id: str
    chunk_index: int
    content: str
    token_count: int
    embedding_model: str
    embedding_model_version: str
    created_at: datetime
