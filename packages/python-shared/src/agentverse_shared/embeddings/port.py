"""The `EmbeddingProvider` port.

Lives in the shared package because apps/worker (embedding chunks at
ingestion) and apps/api (embedding the query at retrieval) must produce
*directly comparable* vectors. Two independent implementations that
drifted on model, dimension, or input normalization would not error —
similarity scores would just quietly become meaningless, which is the
exact silent-degradation failure `vector-database-expert` warns about.

CLAUDE.md Rule 16 in practice: callers depend on this Protocol, never on
a provider SDK. Exactly one file (`openai_provider.py`) imports `openai`,
structurally enforced by
`tests/embeddings/test_rule16_no_direct_openai_imports.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class EmbeddingError(Exception):
    """Base for the shared embedding error taxonomy. Provider-specific
    exceptions are translated at the adapter boundary so callers never
    catch an `openai.*` type (CLAUDE.md §9).
    """


class EmbeddingRateLimitError(EmbeddingError):
    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class EmbeddingAuthError(EmbeddingError):
    pass


class EmbeddingInvalidRequestError(EmbeddingError):
    pass


class EmbeddingUnavailableError(EmbeddingError):
    pass


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """Vectors plus the identity of what produced them.

    `model`/`model_version` travel with the vectors rather than being
    assumed by the caller, so a chunk row can record exactly what
    embedded it — the precondition for never mixing versions in one
    similarity search.
    """

    vectors: list[list[float]]
    model: str
    model_version: str
    #: Tokens the provider billed for this call. Ingestion attributes this
    #: to the workspace, same as any other provider spend.
    prompt_tokens: int


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """Embeds `texts`, returning one vector per input in input order.

        Order is part of the contract: ingestion zips the result back
        against its chunk list, so a provider that reordered results
        would silently attach every embedding to the wrong chunk.
        """
        ...

    @property
    def model(self) -> str: ...

    @property
    def model_version(self) -> str: ...

    @property
    def dimensions(self) -> int: ...
