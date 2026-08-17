"""`ProviderAdapter` implemented against the Anthropic SDK (Phase 11's
second provider — see the port's own docstring: "a second provider
implements the same four methods with zero changes required here or in
any caller").

This is **not** on the real agent-run path — `apps/worker`'s executor
resolves Anthropic models directly through the OpenAI Agents SDK's
`LitellmModel` extension (`apps/worker/.../agents/model_resolution.py`),
never through this class. This adapter exists for `ProviderAdapter`'s
two actual consumers: the internal provider-key-test route and the
in-product docs assistant.

This is the *only* file (alongside `openai_adapter.py`) in this codebase
permitted to `import anthropic` (CLAUDE.md Rule 16) — structurally
enforced by
`tests/orchestration_service/test_rule16_no_direct_anthropic_imports.py`.

Anthropic's Messages API has no OpenAI-style `response_format: json_schema`
mode: `structured_output` gets its schema-constrained output by forcing a
single synthetic tool call (`tool_choice={"type": "tool", "name": ...}`)
and reading the tool call's already-parsed `input` object back — the
closest Anthropic equivalent to "native structured-output mode" per
CLAUDE.md §9.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, TypeVar

import anthropic
from anthropic import AsyncAnthropic

from agentverse_api.orchestration_service.domain.entities import (
    ChatRequest,
    ChatResult,
    RequestedToolCall,
    StreamDelta,
    StreamDone,
    StreamError,
    StreamEvent,
    StructuredOutputRequest,
    StructuredOutputResult,
    TokenUsage,
    ToolCallRequestSpec,
    ToolCallResult,
)
from agentverse_api.orchestration_service.domain.provider_errors import (
    ProviderAuthError,
    ProviderContextLengthError,
    ProviderError,
    ProviderInvalidRequestError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)

T = TypeVar("T")

# Anthropic's own `stop_reason` vocabulary, normalized to the same
# strings `openai_adapter.py` already produces so a consumer (the
# provider-test route's SSE frame, the frontend) never has to know which
# provider answered.
_STOP_REASON_MAP: dict[str, str] = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
    "pause_turn": "stop",
    "refusal": "content_filter",
}


def _normalize_stop_reason(reason: str | None) -> str:
    if reason is None:
        return "stop"
    return _STOP_REASON_MAP.get(reason, reason)


def _extract_retry_after(exc: anthropic.RateLimitError) -> float | None:
    header = exc.response.headers.get("retry-after")
    if header is None:
        return None
    try:
        return float(header)
    except ValueError:
        return None


def _translate_anthropic_error(exc: Exception) -> ProviderError:
    """The one place an Anthropic SDK exception becomes an AgentVerse
    `ProviderError` (CLAUDE.md §9). Mirrors `_translate_openai_error`'s
    conservatism: an unrecognized `APIStatusError` becomes the generic
    base error rather than being guessed into a more specific bucket.
    """
    if isinstance(exc, anthropic.RateLimitError):
        return ProviderRateLimitError(str(exc), retry_after_seconds=_extract_retry_after(exc))
    if isinstance(exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError):
        return ProviderAuthError(str(exc))
    if isinstance(exc, anthropic.BadRequestError):
        message = str(exc).lower()
        if "context" in message and ("too long" in message or "maximum" in message):
            return ProviderContextLengthError(str(exc))
        return ProviderInvalidRequestError(str(exc))
    if isinstance(
        exc,
        anthropic.APIConnectionError | anthropic.InternalServerError | anthropic.OverloadedError,
    ):
        return ProviderUnavailableError(str(exc))
    if isinstance(exc, anthropic.APIError):
        return ProviderError(str(exc))
    return ProviderUnavailableError(str(exc))


def _split_system_prompt(request: ChatRequest) -> tuple[str | None, list[dict[str, Any]]]:
    """Anthropic takes `system` as a top-level request field, not a
    `"system"`-role message — every other role passes through unchanged.
    Multiple system messages are joined; there is normally at most one.
    """
    system_parts = [m.content for m in request.messages if m.role == "system"]
    system = "\n\n".join(system_parts) if system_parts else None
    messages = [
        {"role": m.role, "content": m.content} for m in request.messages if m.role != "system"
    ]
    return system, messages


class AnthropicProviderAdapter:
    """Implements `ProviderAdapter` (structural typing) against
    `anthropic.AsyncAnthropic`.
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        base_url: str | None = None,
        max_retries: int = 3,
        base_delay_seconds: float = 0.5,
        max_delay_seconds: float = 8.0,
        client: AsyncAnthropic | None = None,
    ) -> None:
        # `client` injectable for tests, same rationale as
        # `OpenAIProviderAdapter` — a fake client exercises the real
        # retry/error-translation logic without a live API key.
        self._client = client or AsyncAnthropic(
            api_key=api_key, base_url=base_url, max_retries=0
        )
        self._max_retries = max_retries
        self._base_delay_seconds = base_delay_seconds
        self._max_delay_seconds = max_delay_seconds

    async def _retry_rate_limits(self, call: Callable[[], Awaitable[T]]) -> T:
        attempt = 0
        while True:
            try:
                return await call()
            except anthropic.RateLimitError as exc:
                attempt += 1
                if attempt > self._max_retries:
                    raise _translate_anthropic_error(exc) from exc
                delay = min(
                    self._base_delay_seconds * (2 ** (attempt - 1)),
                    self._max_delay_seconds,
                )
                delay += random.uniform(0, delay * 0.25)
                await asyncio.sleep(delay)
            except Exception as exc:
                raise _translate_anthropic_error(exc) from exc

    async def chat(self, request: ChatRequest) -> ChatResult:
        system, messages = _split_system_prompt(request)

        async def _call() -> Any:
            kwargs: dict[str, Any] = {
                "model": request.model,
                "messages": messages,
                "max_tokens": request.max_output_tokens or 4096,
            }
            if system is not None:
                kwargs["system"] = system
            if request.temperature is not None:
                kwargs["temperature"] = request.temperature
            return await self._client.messages.create(**kwargs)

        response = await self._retry_rate_limits(_call)
        text = "".join(block.text for block in response.content if block.type == "text")
        usage = TokenUsage(
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )
        return ChatResult(
            content=text,
            usage=usage,
            finish_reason=_normalize_stop_reason(response.stop_reason),
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        system, messages = _split_system_prompt(request)
        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_output_tokens or 4096,
        }
        if system is not None:
            kwargs["system"] = system
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature

        # Retries (bounded, 429-only) apply to *opening* the stream only —
        # same scope `openai_adapter.stream_chat` retries at (obtaining
        # `stream`, never a chunk mid-iteration). A rate limit mid-stream
        # is translated below like any other mid-stream failure, not
        # retried: there is no cheap way to resume a partial stream.
        async def _open() -> Any:
            manager = self._client.messages.stream(**kwargs)
            return manager, await manager.__aenter__()

        try:
            manager, stream = await self._retry_rate_limits(_open)
        except ProviderError as exc:
            yield StreamError(
                code=exc.code,
                message=exc.message,
                retry_after_seconds=getattr(exc, "retry_after_seconds", None),
            )
            return

        try:
            async for text in stream.text_stream:
                if text:
                    yield StreamDelta(text=text)
            final = await stream.get_final_message()
        except Exception as exc:
            translated = _translate_anthropic_error(exc)
            yield StreamError(
                code=translated.code,
                message=translated.message,
                retry_after_seconds=getattr(translated, "retry_after_seconds", None),
            )
            return
        finally:
            await manager.__aexit__(None, None, None)

        yield StreamDone(
            finish_reason=_normalize_stop_reason(final.stop_reason),
            usage=TokenUsage(
                prompt_tokens=final.usage.input_tokens,
                completion_tokens=final.usage.output_tokens,
            ),
        )

    async def call_tool(self, request: ToolCallRequestSpec) -> ToolCallResult:
        # Built as `dict[str, Any]` and passed via `**kwargs`, same as
        # `chat()`/`stream_chat()` above: the SDK's `create()` overloads
        # are narrow, generated typed-dict unions this codebase's own
        # provider-neutral `ToolSchema`/`ChatMessage` shapes are never
        # going to satisfy structurally — real type safety for this
        # boundary begins at `ToolCallResult`/`RequestedToolCall`, not at
        # the raw SDK call.
        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "max_tokens": 4096,
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.parameters_json_schema,
                }
                for tool in request.tools
            ],
        }

        async def _call() -> Any:
            return await self._client.messages.create(**kwargs)

        response = await self._retry_rate_limits(_call)
        text_parts = [block.text for block in response.content if block.type == "text"]
        tool_calls = [
            RequestedToolCall(
                id=block.id,
                name=block.name,
                arguments_json=json.dumps(block.input),
            )
            for block in response.content
            if block.type == "tool_use"
        ]
        usage = TokenUsage(
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )
        return ToolCallResult(
            content="".join(text_parts) or None, tool_calls=tool_calls, usage=usage
        )

    async def structured_output(self, request: StructuredOutputRequest) -> StructuredOutputResult:
        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "max_tokens": 4096,
            "tools": [
                {
                    "name": request.schema_name,
                    "description": f"Emit output matching the {request.schema_name} schema.",
                    "input_schema": request.json_schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": request.schema_name},
        }

        async def _call() -> Any:
            return await self._client.messages.create(**kwargs)

        response = await self._retry_rate_limits(_call)
        data: dict[str, object] = {}
        for block in response.content:
            if block.type == "tool_use" and block.name == request.schema_name:
                data = block.input
                break
        usage = TokenUsage(
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )
        return StructuredOutputResult(data=data, usage=usage)
