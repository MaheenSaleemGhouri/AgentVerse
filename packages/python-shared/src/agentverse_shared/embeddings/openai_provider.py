"""`EmbeddingProvider` implemented against the OpenAI SDK.

The *only* file in the shared package permitted to `import openai`
(CLAUDE.md Rule 16), enforced by
`tests/embeddings/test_rule16_no_direct_openai_imports.py`. Mirrors the
error-translation and backoff discipline already established in
apps/api's `orchestration_service/infrastructure/providers/openai_adapter.py`
rather than inventing a second convention.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable

import openai
from openai import AsyncOpenAI

from agentverse_shared.embeddings.port import (
    EmbeddingAuthError,
    EmbeddingError,
    EmbeddingInvalidRequestError,
    EmbeddingProvider,
    EmbeddingRateLimitError,
    EmbeddingResult,
    EmbeddingUnavailableError,
)

#: Model → dimensionality. Must agree with `kb_chunks.embedding`'s fixed
#: width; a model with different dimensions needs a schema migration plus
#: a backfill/cutover, never a config swap (ADR-0003).
MODEL_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}

#: OpenAI's documented per-request input cap for the embeddings endpoint.
#: Callers batch below this; exceeding it is a hard provider error, not a
#: degradation, so it is validated locally rather than discovered remotely.
MAX_INPUTS_PER_REQUEST = 2048

_MAX_ATTEMPTS = 4
_BASE_DELAY_SECONDS = 0.5


def _retry_after(exc: openai.RateLimitError) -> float | None:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    header = response.headers.get("retry-after")
    if header is None:
        return None
    try:
        return float(header)
    except ValueError:
        return None


def _translate(exc: Exception) -> EmbeddingError:
    """One place an OpenAI exception becomes an AgentVerse embedding
    error. Deliberately conservative: an unrecognized `APIError` maps to
    the generic base rather than being guessed into a specific bucket.
    """
    if isinstance(exc, openai.RateLimitError):
        return EmbeddingRateLimitError(str(exc), retry_after_seconds=_retry_after(exc))
    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        return EmbeddingAuthError(str(exc))
    if isinstance(exc, openai.BadRequestError):
        return EmbeddingInvalidRequestError(str(exc))
    if isinstance(exc, openai.APIConnectionError | openai.InternalServerError):
        return EmbeddingUnavailableError(str(exc))
    if isinstance(exc, openai.APIError):
        return EmbeddingError(str(exc))
    return EmbeddingError(str(exc))


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-3-small",
        model_version: str = "1",
        base_url: str | None = None,
        client: AsyncOpenAI | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        if model not in MODEL_DIMENSIONS:
            raise ValueError(f"Unknown embedding model: {model}")
        self._model = model
        self._model_version = model_version
        # An injected client keeps this unit-testable without patching
        # module globals (CLAUDE.md §11: dependency-injected clients).
        self._client = client or AsyncOpenAI(api_key=api_key, base_url=base_url)
        # Injectable so retry tests assert backoff *behavior* without
        # actually sleeping through it — otherwise exercising the retry
        # path costs seconds per test and the fast suite stops being fast.
        self._sleep = sleep or asyncio.sleep

    @property
    def model(self) -> str:
        return self._model

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def dimensions(self) -> int:
        return MODEL_DIMENSIONS[self._model]

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(
                vectors=[], model=self._model, model_version=self._model_version, prompt_tokens=0
            )
        if len(texts) > MAX_INPUTS_PER_REQUEST:
            raise EmbeddingInvalidRequestError(
                f"{len(texts)} inputs exceeds the per-request cap of {MAX_INPUTS_PER_REQUEST}"
            )

        response = await self._with_backoff(texts)

        # Sort by the provider's own index rather than trusting response
        # order: the port promises input order, and ingestion zips the
        # result straight back onto its chunk list — a reordering here
        # would attach every vector to the wrong chunk, silently.
        items = sorted(response.data, key=lambda item: item.index)
        if len(items) != len(texts):
            raise EmbeddingError(
                f"provider returned {len(items)} embeddings for {len(texts)} inputs"
            )

        vectors = [list(item.embedding) for item in items]
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise EmbeddingError(
                    f"expected {self.dimensions}-dim vectors from {self._model}, got {len(vector)}"
                )

        return EmbeddingResult(
            vectors=vectors,
            model=self._model,
            model_version=self._model_version,
            prompt_tokens=response.usage.prompt_tokens,
        )

    async def _with_backoff(self, texts: list[str]) -> openai.types.CreateEmbeddingResponse:
        """Bounded exponential backoff with jitter on transient failures
        (CLAUDE.md §9). Auth/invalid-request errors are not retried —
        they will fail identically every time.
        """
        last: EmbeddingError | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                return await self._client.embeddings.create(model=self._model, input=texts)
            except Exception as exc:
                translated = _translate(exc)
                if (
                    isinstance(translated, EmbeddingAuthError | EmbeddingInvalidRequestError)
                    or attempt == _MAX_ATTEMPTS - 1
                ):
                    raise translated from exc
                last = translated
                delay = _BASE_DELAY_SECONDS * (2**attempt)
                if isinstance(translated, EmbeddingRateLimitError) and (
                    translated.retry_after_seconds is not None
                ):
                    delay = max(delay, translated.retry_after_seconds)
                await self._sleep(delay + random.uniform(0, 0.25))

        raise last if last is not None else EmbeddingError("embedding failed")


async def embed_in_batches(
    provider: EmbeddingProvider,
    texts: list[str],
    *,
    batch_size: int = 128,
) -> EmbeddingResult:
    """Embeds an arbitrarily long list by chunking into provider calls.

    Batching is here, not in `embed`, so the port stays a single
    round-trip primitive and the batching policy is visible to callers
    (`vector-database-expert`: batch processing is an explicit
    requirement, and a 5,000-chunk document must not become 5,000 calls).
    """
    if batch_size < 1 or batch_size > MAX_INPUTS_PER_REQUEST:
        raise ValueError(f"batch_size must be in 1..{MAX_INPUTS_PER_REQUEST}")

    all_vectors: list[list[float]] = []
    total_tokens = 0
    for start in range(0, len(texts), batch_size):
        result = await provider.embed(texts[start : start + batch_size])
        all_vectors.extend(result.vectors)
        total_tokens += result.prompt_tokens

    return EmbeddingResult(
        vectors=all_vectors,
        model=provider.model,
        model_version=provider.model_version,
        prompt_tokens=total_tokens,
    )
