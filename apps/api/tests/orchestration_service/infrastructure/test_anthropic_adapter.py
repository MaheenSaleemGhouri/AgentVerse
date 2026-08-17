"""Adapter-level tests for `AnthropicProviderAdapter`, mirroring
`test_openai_adapter.py`'s coverage: bounded retry/backoff on 429s, and
error translation at the boundary. A fake Anthropic-shaped client is
injected via `AnthropicProviderAdapter(client=...)` so these tests never
touch the real network (CLAUDE.md §11) yet still exercise real
`anthropic.*` exception types.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from agentverse_api.orchestration_service.domain.entities import (
    ChatMessage,
    ChatRequest,
    StreamDelta,
    StreamDone,
    StreamError,
    StructuredOutputRequest,
    ToolCallRequestSpec,
    ToolSchema,
)
from agentverse_api.orchestration_service.domain.provider_errors import (
    ProviderAuthError,
    ProviderContextLengthError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from agentverse_api.orchestration_service.infrastructure.providers.anthropic_adapter import (
    AnthropicProviderAdapter,
)


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _rate_limit_error(retry_after: str | None = None) -> anthropic.RateLimitError:
    headers = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(status_code=429, request=_request(), headers=headers)
    return anthropic.RateLimitError("rate limited", response=response, body=None)


def _auth_error() -> anthropic.AuthenticationError:
    response = httpx.Response(status_code=401, request=_request())
    return anthropic.AuthenticationError("bad key", response=response, body=None)


def _bad_request_error(message: str) -> anthropic.BadRequestError:
    response = httpx.Response(status_code=400, request=_request())
    return anthropic.BadRequestError(message, response=response, body=None)


def _connection_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(request=_request())


def _text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _tool_block(*, id: str, name: str, input: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input)


def _message(
    *,
    content: list[object],
    stop_reason: str = "end_turn",
    input_tokens: int = 5,
    output_tokens: int = 3,
) -> SimpleNamespace:
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


class _FakeMessagesCreate:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeStreamManager:
    """One `messages.stream(...)` attempt. `open_error`, if set, is raised
    from `__aenter__` — the real SDK only makes the request on context-
    manager entry, so that is where a rate-limit error actually surfaces,
    not from `stream()` itself (which is synchronous and never raises).
    """

    def __init__(
        self,
        deltas: list[str] | None = None,
        final_message: object = None,
        *,
        open_error: Exception | None = None,
    ) -> None:
        self._deltas = deltas or []
        self._final = final_message
        self._open_error = open_error

    async def __aenter__(self) -> _FakeStreamManager:
        if self._open_error is not None:
            raise self._open_error
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False

    @property
    def text_stream(self) -> AsyncIterator[str]:
        return self._aiter()

    async def _aiter(self) -> AsyncIterator[str]:
        for delta in self._deltas:
            yield delta

    async def get_final_message(self) -> object:
        return self._final


class _FakeMessages:
    def __init__(
        self,
        create_responses: list[object] | None = None,
        stream_managers: list[_FakeStreamManager] | None = None,
    ) -> None:
        self._create = _FakeMessagesCreate(create_responses or [])
        self._stream_managers = list(stream_managers or [])

    async def create(self, **kwargs: object) -> object:
        return await self._create.create(**kwargs)

    def stream(self, **kwargs: object) -> _FakeStreamManager:
        # Every retry attempt calls `messages.stream(...)` fresh (a new
        # manager per attempt), matching the real SDK.
        return self._stream_managers.pop(0)


class _FakeAnthropicClient:
    def __init__(
        self,
        create_responses: list[object] | None = None,
        stream_managers: list[_FakeStreamManager] | None = None,
    ) -> None:
        self.messages = _FakeMessages(create_responses, stream_managers)


def _adapter(
    responses: list[object] | None = None,
    *,
    stream_managers: list[_FakeStreamManager] | None = None,
    max_retries: int = 3,
) -> AnthropicProviderAdapter:
    return AnthropicProviderAdapter(
        client=_FakeAnthropicClient(responses, stream_managers),  # type: ignore[arg-type]
        max_retries=max_retries,
        base_delay_seconds=0.001,
        max_delay_seconds=0.005,
    )


def _request_payload() -> ChatRequest:
    return ChatRequest(
        model="anthropic/claude-haiku-4-5", messages=[ChatMessage(role="user", content="hi")]
    )


@pytest.mark.asyncio
async def test_chat_succeeds_first_try() -> None:
    adapter = _adapter([_message(content=[_text_block("hello")])])
    result = await adapter.chat(_request_payload())
    assert result.content == "hello"
    assert result.usage.prompt_tokens == 5
    assert result.finish_reason == "stop"


@pytest.mark.asyncio
async def test_chat_splits_system_role_into_top_level_system_param() -> None:
    adapter = _adapter([_message(content=[_text_block("hi")])])
    request = ChatRequest(
        model="anthropic/claude-haiku-4-5",
        messages=[
            ChatMessage(role="system", content="Be terse."),
            ChatMessage(role="user", content="hi"),
        ],
    )
    await adapter.chat(request)
    call = adapter._client.messages._create.calls[0]  # type: ignore[attr-defined]
    assert call["system"] == "Be terse."
    assert call["messages"] == [{"role": "user", "content": "hi"}]


@pytest.mark.asyncio
async def test_chat_retries_rate_limit_then_succeeds() -> None:
    adapter = _adapter(
        [_rate_limit_error(), _rate_limit_error(), _message(content=[_text_block("hi")])]
    )
    result = await adapter.chat(_request_payload())
    assert result.content == "hi"


@pytest.mark.asyncio
async def test_chat_exhausts_retries_and_raises_rate_limit_error() -> None:
    adapter = _adapter(
        [_rate_limit_error(), _rate_limit_error(), _rate_limit_error()], max_retries=2
    )
    with pytest.raises(ProviderRateLimitError):
        await adapter.chat(_request_payload())


@pytest.mark.asyncio
async def test_chat_does_not_retry_auth_errors() -> None:
    adapter = _adapter([_auth_error(), _message(content=[_text_block("hi")])])
    with pytest.raises(ProviderAuthError):
        await adapter.chat(_request_payload())
    assert len(adapter._client.messages._create.calls) == 1  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_bad_request_context_length_translated() -> None:
    adapter = _adapter([_bad_request_error("prompt is too long: maximum context exceeded")])
    with pytest.raises(ProviderContextLengthError):
        await adapter.chat(_request_payload())


@pytest.mark.asyncio
async def test_connection_error_translated_to_provider_unavailable() -> None:
    adapter = _adapter([_connection_error()])
    with pytest.raises(ProviderUnavailableError):
        await adapter.chat(_request_payload())


@pytest.mark.asyncio
async def test_stream_chat_yields_deltas_then_done() -> None:
    manager = _FakeStreamManager(
        ["Hel", "lo"], _message(content=[_text_block("Hello")], stop_reason="end_turn")
    )
    adapter = _adapter(stream_managers=[manager])
    events = [event async for event in adapter.stream_chat(_request_payload())]
    assert events[0] == StreamDelta(text="Hel")
    assert events[1] == StreamDelta(text="lo")
    assert isinstance(events[-1], StreamDone)
    assert events[-1].finish_reason == "stop"
    assert events[-1].usage.prompt_tokens == 5


@pytest.mark.asyncio
async def test_stream_chat_yields_stream_error_when_rate_limited_beyond_ceiling() -> None:
    # max_retries=2: 3 consecutive 429s on *opening* the stream exceeds
    # the ceiling — same scope `test_chat_exhausts_retries_...` covers
    # for `chat()`, applied to `stream_chat()`'s own retry wrapping of
    # `messages.stream(...)`'s entry.
    managers = [
        _FakeStreamManager(open_error=_rate_limit_error()),
        _FakeStreamManager(open_error=_rate_limit_error()),
        _FakeStreamManager(open_error=_rate_limit_error()),
    ]
    adapter = _adapter(stream_managers=managers, max_retries=2)
    events = [event async for event in adapter.stream_chat(_request_payload())]
    assert len(events) == 1
    assert isinstance(events[0], StreamError)
    assert events[0].code == "rate_limited"


@pytest.mark.asyncio
async def test_call_tool_returns_requested_tool_calls() -> None:
    adapter = _adapter(
        [
            _message(
                content=[_tool_block(id="tool_1", name="lookup", input={"query": "weather"})],
                stop_reason="tool_use",
            )
        ]
    )
    request = ToolCallRequestSpec(
        model="anthropic/claude-haiku-4-5",
        messages=[ChatMessage(role="user", content="what's the weather")],
        tools=[
            ToolSchema(
                name="lookup",
                description="Look something up.",
                parameters_json_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            )
        ],
    )
    result = await adapter.call_tool(request)
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "lookup"
    assert result.tool_calls[0].arguments_json == '{"query": "weather"}'


@pytest.mark.asyncio
async def test_structured_output_reads_forced_tool_call_input() -> None:
    adapter = _adapter(
        [
            _message(
                content=[
                    _tool_block(
                        id="tool_1", name="triage_result", input={"category": "billing"}
                    )
                ],
                stop_reason="tool_use",
            )
        ]
    )
    request = StructuredOutputRequest(
        model="anthropic/claude-haiku-4-5",
        messages=[ChatMessage(role="user", content="triage this")],
        json_schema={"type": "object", "properties": {"category": {"type": "string"}}},
        schema_name="triage_result",
    )
    result = await adapter.structured_output(request)
    assert result.data == {"category": "billing"}
    call = adapter._client.messages._create.calls[0]  # type: ignore[attr-defined]
    assert call["tool_choice"] == {"type": "tool", "name": "triage_result"}
