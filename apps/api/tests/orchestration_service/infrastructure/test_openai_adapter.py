"""Adapter-level tests: retry/backoff bounded ceiling on 429s, and error
translation at the boundary — the two properties this phase's
acceptance criteria name explicitly. A fake OpenAI-shaped client is
injected via `OpenAIProviderAdapter(client=...)` so these tests never
touch the real network (CLAUDE.md §11) yet still exercise real
`openai.*` exception types, not stand-ins.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import openai
import pytest

from agentverse_api.orchestration_service.domain.entities import (
    ChatMessage,
    ChatRequest,
    StreamDelta,
    StreamDone,
    StreamError,
)
from agentverse_api.orchestration_service.domain.provider_errors import (
    ProviderAuthError,
    ProviderContentFilterError,
    ProviderContextLengthError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from agentverse_api.orchestration_service.infrastructure.providers.openai_adapter import (
    OpenAIProviderAdapter,
)


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def _rate_limit_error(retry_after: str | None = None) -> openai.RateLimitError:
    headers = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(status_code=429, request=_request(), headers=headers)
    return openai.RateLimitError("rate limited", response=response, body=None)


def _auth_error() -> openai.AuthenticationError:
    response = httpx.Response(status_code=401, request=_request())
    return openai.AuthenticationError("bad key", response=response, body=None)


def _bad_request_error(message: str) -> openai.BadRequestError:
    response = httpx.Response(status_code=400, request=_request())
    return openai.BadRequestError(message, response=response, body=None)


def _connection_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(message="connection failed", request=_request())


def _chat_response(*, content: str = "hi", finish_reason: str = "stop") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(content=content, tool_calls=None),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=3),
    )


class _FakeStream:
    def __init__(self, chunks: list[object]) -> None:
        self._chunks = list(chunks)

    def __aiter__(self) -> _FakeStream:
        return self

    async def __anext__(self) -> object:
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


def _delta_chunk(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        usage=None,
        choices=[SimpleNamespace(finish_reason=None, delta=SimpleNamespace(content=text))],
    )


def _done_chunk(*, prompt_tokens: int = 5, completion_tokens: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
        choices=[SimpleNamespace(finish_reason="stop", delta=SimpleNamespace(content=None))],
    )


class _FakeCompletions:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeOpenAIClient:
    def __init__(self, responses: list[object]) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(responses))


def _adapter(responses: list[object], *, max_retries: int = 3) -> OpenAIProviderAdapter:
    return OpenAIProviderAdapter(
        client=_FakeOpenAIClient(responses),  # type: ignore[arg-type]
        max_retries=max_retries,
        base_delay_seconds=0.001,
        max_delay_seconds=0.005,
    )


def _request_payload() -> ChatRequest:
    return ChatRequest(model="gpt-4o-mini", messages=[ChatMessage(role="user", content="hi")])


@pytest.mark.asyncio
async def test_chat_succeeds_first_try() -> None:
    adapter = _adapter([_chat_response(content="hello")])
    result = await adapter.chat(_request_payload())
    assert result.content == "hello"
    assert result.usage.prompt_tokens == 5


@pytest.mark.asyncio
async def test_chat_retries_rate_limit_then_succeeds() -> None:
    adapter = _adapter([_rate_limit_error(), _rate_limit_error(), _chat_response()])
    result = await adapter.chat(_request_payload())
    assert result.content == "hi"


@pytest.mark.asyncio
async def test_chat_exhausts_retries_and_raises_rate_limit_error() -> None:
    # max_retries=2: 3 consecutive 429s exceeds the ceiling.
    adapter = _adapter(
        [_rate_limit_error(), _rate_limit_error(), _rate_limit_error()], max_retries=2
    )
    with pytest.raises(ProviderRateLimitError):
        await adapter.chat(_request_payload())


@pytest.mark.asyncio
async def test_chat_does_not_retry_auth_errors() -> None:
    adapter = _adapter([_auth_error(), _chat_response()])
    with pytest.raises(ProviderAuthError):
        await adapter.chat(_request_payload())
    # Only one call was made — no retry on a non-429 error.
    assert len(adapter._client.chat.completions.calls) == 1  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_bad_request_context_length_translated() -> None:
    adapter = _adapter([_bad_request_error("maximum context length exceeded")])
    with pytest.raises(ProviderContextLengthError):
        await adapter.chat(_request_payload())


@pytest.mark.asyncio
async def test_bad_request_content_filter_translated() -> None:
    adapter = _adapter([_bad_request_error("Content flagged by content_filter policy")])
    with pytest.raises(ProviderContentFilterError):
        await adapter.chat(_request_payload())


@pytest.mark.asyncio
async def test_connection_error_translated_to_provider_unavailable() -> None:
    adapter = _adapter([_connection_error()])
    with pytest.raises(ProviderUnavailableError):
        await adapter.chat(_request_payload())


@pytest.mark.asyncio
async def test_stream_chat_yields_deltas_then_done() -> None:
    stream = _FakeStream([_delta_chunk("Hel"), _delta_chunk("lo"), _done_chunk()])
    adapter = _adapter([stream])
    events = [event async for event in adapter.stream_chat(_request_payload())]
    assert events[0] == StreamDelta(text="Hel")
    assert events[1] == StreamDelta(text="lo")
    assert isinstance(events[-1], StreamDone)
    assert events[-1].usage.prompt_tokens == 5


@pytest.mark.asyncio
async def test_stream_chat_yields_stream_error_when_rate_limited_beyond_ceiling() -> None:
    adapter = _adapter(
        [_rate_limit_error(), _rate_limit_error(), _rate_limit_error()], max_retries=2
    )
    events = [event async for event in adapter.stream_chat(_request_payload())]
    assert len(events) == 1
    assert isinstance(events[0], StreamError)
    assert events[0].code == "rate_limited"
