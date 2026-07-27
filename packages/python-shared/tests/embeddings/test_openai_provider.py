"""Embedding provider tests with a fake OpenAI client — no network.

The provider is injected with a stand-in client rather than patching
module globals (CLAUDE.md §11: dependency-injected clients are mockable).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import openai
import pytest

from agentverse_shared.embeddings.openai_provider import (
    MAX_INPUTS_PER_REQUEST,
    OpenAIEmbeddingProvider,
    embed_in_batches,
)
from agentverse_shared.embeddings.port import (
    EmbeddingAuthError,
    EmbeddingError,
    EmbeddingInvalidRequestError,
    EmbeddingRateLimitError,
)

DIM = 1536


@dataclass
class _Item:
    index: int
    embedding: list[float]


@dataclass
class _Usage:
    prompt_tokens: int


@dataclass
class _Response:
    data: list[_Item]
    usage: _Usage


class _FakeEmbeddings:
    def __init__(self, parent: _FakeClient) -> None:
        self._parent = parent

    async def create(self, *, model: str, input: list[str]) -> Any:
        self._parent.calls.append(list(input))
        if self._parent.raise_exc is not None:
            exc = self._parent.raise_exc
            # Raise a limited number of times, then succeed — lets a test
            # assert retry behavior rather than only terminal failure.
            if self._parent.raise_times > 0:
                self._parent.raise_times -= 1
                raise exc
        return _Response(
            data=[
                _Item(index=i, embedding=self._parent.vector_for(i, text))
                for i, text in enumerate(input)
            ],
            usage=_Usage(prompt_tokens=sum(len(t.split()) for t in input)),
        )


class _FakeClient:
    def __init__(
        self,
        *,
        dim: int = DIM,
        raise_exc: Exception | None = None,
        raise_times: int = 0,
    ) -> None:
        self.embeddings = _FakeEmbeddings(self)
        self.calls: list[list[str]] = []
        self.dim = dim
        self.raise_exc = raise_exc
        self.raise_times = raise_times

    def vector_for(self, i: int, text: str) -> list[float]:
        return [float(i)] * self.dim


class _RecordingSleep:
    """No-op sleep that records requested delays, so retry tests assert
    backoff behavior without spending real wall-clock time on it.
    """

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def _provider(client: Any, sleep: Any = None) -> OpenAIEmbeddingProvider:
    return OpenAIEmbeddingProvider(
        api_key="not-used", client=client, sleep=sleep or _RecordingSleep()
    )


# --- happy path ---------------------------------------------------------


async def test_returns_one_vector_per_input() -> None:
    provider = _provider(_FakeClient())

    result = await provider.embed(["alpha", "beta", "gamma"])

    assert len(result.vectors) == 3
    assert all(len(v) == DIM for v in result.vectors)


async def test_result_carries_model_identity_for_the_chunk_row() -> None:
    # These travel onto kb_chunks so retrieval can filter by them; a
    # provider that omitted them would make version-mixing undetectable.
    provider = OpenAIEmbeddingProvider(
        api_key="x", model="text-embedding-3-small", model_version="7", client=_FakeClient()
    )

    result = await provider.embed(["one"])

    assert result.model == "text-embedding-3-small"
    assert result.model_version == "7"


async def test_reports_prompt_tokens_for_usage_attribution() -> None:
    result = await _provider(_FakeClient()).embed(["two words", "three more words"])

    assert result.prompt_tokens == 5


async def test_empty_input_makes_no_provider_call() -> None:
    client = _FakeClient()

    result = await _provider(client).embed([])

    assert result.vectors == []
    assert client.calls == []


async def test_dimensions_reflect_the_model() -> None:
    assert _provider(_FakeClient()).dimensions == 1536
    large = OpenAIEmbeddingProvider(
        api_key="x", model="text-embedding-3-large", client=_FakeClient(dim=3072)
    )
    assert large.dimensions == 3072


def test_unknown_model_is_rejected_at_construction() -> None:
    # Failing loudly here beats discovering a dimension mismatch after
    # writing thousands of unusable vectors.
    with pytest.raises(ValueError, match="Unknown embedding model"):
        OpenAIEmbeddingProvider(api_key="x", model="text-embedding-9-imaginary")


# --- ordering and shape guarantees -------------------------------------


async def test_vectors_are_returned_in_input_order_even_if_provider_reorders() -> None:
    """The port promises input order because ingestion zips vectors back
    onto its chunk list. Out-of-order results must be re-sorted, not
    passed through, or every chunk gets the wrong embedding.
    """

    class _ShuffledEmbeddings(_FakeEmbeddings):
        async def create(self, *, model: str, input: list[str]) -> Any:
            items = [_Item(index=i, embedding=[float(i)] * DIM) for i in range(len(input))]
            return _Response(data=list(reversed(items)), usage=_Usage(prompt_tokens=1))

    client = _FakeClient()
    client.embeddings = _ShuffledEmbeddings(client)

    result = await _provider(client).embed(["a", "b", "c"])

    assert [v[0] for v in result.vectors] == [0.0, 1.0, 2.0]


async def test_count_mismatch_is_an_error_not_a_silent_truncation() -> None:
    class _ShortEmbeddings(_FakeEmbeddings):
        async def create(self, *, model: str, input: list[str]) -> Any:
            return _Response(
                data=[_Item(index=0, embedding=[0.0] * DIM)], usage=_Usage(prompt_tokens=1)
            )

    client = _FakeClient()
    client.embeddings = _ShortEmbeddings(client)

    with pytest.raises(EmbeddingError, match="returned 1 embeddings for 3 inputs"):
        await _provider(client).embed(["a", "b", "c"])


async def test_wrong_dimensionality_is_rejected() -> None:
    # A silently wrong width would be written to a fixed-width pgvector
    # column and fail far from the cause.
    client = _FakeClient(dim=8)

    with pytest.raises(EmbeddingError, match="expected 1536-dim"):
        await _provider(client).embed(["a"])


async def test_oversized_request_is_rejected_locally() -> None:
    with pytest.raises(EmbeddingInvalidRequestError, match="exceeds the per-request cap"):
        await _provider(_FakeClient()).embed(["x"] * (MAX_INPUTS_PER_REQUEST + 1))


# --- error translation and retry ---------------------------------------


async def test_auth_error_is_translated_and_not_retried() -> None:
    client = _FakeClient(
        raise_exc=openai.AuthenticationError("bad key", response=_FakeHTTPResponse(401), body=None),
        raise_times=99,
    )

    with pytest.raises(EmbeddingAuthError):
        await _provider(client).embed(["a"])

    # Retrying a bad key just wastes time — it fails identically forever.
    assert len(client.calls) == 1


async def test_bad_request_is_translated_and_not_retried() -> None:
    client = _FakeClient(
        raise_exc=openai.BadRequestError("nope", response=_FakeHTTPResponse(400), body=None),
        raise_times=99,
    )

    with pytest.raises(EmbeddingInvalidRequestError):
        await _provider(client).embed(["a"])

    assert len(client.calls) == 1


async def test_rate_limit_is_retried_then_succeeds() -> None:
    client = _FakeClient(
        raise_exc=openai.RateLimitError("slow down", response=_FakeHTTPResponse(429), body=None),
        raise_times=2,
    )
    sleep = _RecordingSleep()

    result = await _provider(client, sleep).embed(["a"])

    assert len(result.vectors) == 1
    assert len(client.calls) == 3  # two failures, then success
    # Backoff must actually grow, not hammer the provider at a fixed rate.
    assert len(sleep.delays) == 2
    assert sleep.delays[1] > sleep.delays[0]


async def test_retry_honors_a_retry_after_header_longer_than_the_backoff() -> None:
    client = _FakeClient(
        raise_exc=openai.RateLimitError(
            "slow down", response=_FakeHTTPResponse(429, retry_after="30"), body=None
        ),
        raise_times=1,
    )
    sleep = _RecordingSleep()

    await _provider(client, sleep).embed(["a"])

    # Ignoring a server-sent Retry-After just earns another 429.
    assert sleep.delays[0] >= 30


async def test_retry_attempts_are_bounded() -> None:
    client = _FakeClient(
        raise_exc=openai.RateLimitError("nope", response=_FakeHTTPResponse(429), body=None),
        raise_times=99,
    )
    sleep = _RecordingSleep()

    with pytest.raises(EmbeddingRateLimitError):
        await _provider(client, sleep).embed(["a"])

    # An unbounded retry loop on a persistently rate-limited provider
    # would wedge the ingestion worker indefinitely.
    assert len(client.calls) == 4


async def test_persistent_rate_limit_surfaces_the_translated_error() -> None:
    client = _FakeClient(
        raise_exc=openai.RateLimitError("nope", response=_FakeHTTPResponse(429), body=None),
        raise_times=99,
    )

    with pytest.raises(EmbeddingRateLimitError):
        await _provider(client).embed(["a"])


async def test_no_openai_exception_type_escapes_the_adapter() -> None:
    # Callers must never have to catch an openai.* type (CLAUDE.md §9).
    client = _FakeClient(
        raise_exc=openai.APIConnectionError(request=None),  # type: ignore[arg-type]
        raise_times=99,
    )

    with pytest.raises(EmbeddingError) as excinfo:
        await _provider(client).embed(["a"])

    assert not isinstance(excinfo.value, openai.APIError)


# --- batching -----------------------------------------------------------


async def test_batching_splits_into_multiple_provider_calls() -> None:
    client = _FakeClient()

    result = await embed_in_batches(
        _provider(client), [f"t{i}" for i in range(250)], batch_size=100
    )

    assert len(result.vectors) == 250
    assert [len(c) for c in client.calls] == [100, 100, 50]


async def test_batching_sums_token_usage_across_calls() -> None:
    client = _FakeClient()

    result = await embed_in_batches(_provider(client), ["one word"] * 4, batch_size=2)

    assert result.prompt_tokens == 8


async def test_batching_preserves_overall_order() -> None:
    client = _FakeClient()

    result = await embed_in_batches(_provider(client), [f"t{i}" for i in range(5)], batch_size=2)

    # Per-batch indexes restart, so a naive implementation would emit
    # 0,1,0,1,0 — order across batch seams is what this pins down.
    assert [v[0] for v in result.vectors] == [0.0, 1.0, 0.0, 1.0, 0.0]


async def test_empty_list_batches_to_nothing() -> None:
    client = _FakeClient()

    result = await embed_in_batches(_provider(client), [], batch_size=10)

    assert result.vectors == []
    assert client.calls == []


@pytest.mark.parametrize("bad", [0, -1, MAX_INPUTS_PER_REQUEST + 1])
async def test_invalid_batch_size_is_rejected(bad: int) -> None:
    with pytest.raises(ValueError, match="batch_size must be"):
        await embed_in_batches(_provider(_FakeClient()), ["a"], batch_size=bad)


class _FakeHTTPResponse:
    """Minimal stand-in for the httpx response openai's exceptions carry."""

    def __init__(self, status_code: int, retry_after: str | None = None) -> None:
        self.status_code = status_code
        self.headers = {"retry-after": retry_after} if retry_after else {}
        self.request = None
