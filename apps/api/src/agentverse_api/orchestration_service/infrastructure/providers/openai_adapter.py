"""`ProviderAdapter` implemented against the OpenAI SDK.

This is the *only* file in this codebase permitted to `import openai`
(CLAUDE.md Rule 16) — structurally enforced by
`tests/orchestration_service/test_rule16_no_direct_openai_imports.py`,
which greps every other file for `import openai` and fails the build if
it finds one.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, TypeVar

import openai
from openai import AsyncOpenAI

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
    ProviderContentFilterError,
    ProviderContextLengthError,
    ProviderError,
    ProviderInvalidRequestError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)

T = TypeVar("T")


def _extract_retry_after(exc: openai.RateLimitError) -> float | None:
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


def _translate_openai_error(exc: Exception) -> ProviderError:
    """The one place an OpenAI SDK exception becomes an AgentVerse
    `ProviderError` (CLAUDE.md §9: providers errors translated at the
    boundary). Every branch is deliberately conservative: an
    unrecognized `APIError` becomes the generic base error rather than
    being guessed into a more specific (and possibly wrong) bucket.
    """
    if isinstance(exc, openai.RateLimitError):
        return ProviderRateLimitError(str(exc), retry_after_seconds=_extract_retry_after(exc))
    if isinstance(exc, openai.AuthenticationError):
        return ProviderAuthError(str(exc))
    if isinstance(exc, openai.BadRequestError):
        message = str(exc).lower()
        if "context_length" in message or "maximum context length" in message:
            return ProviderContextLengthError(str(exc))
        if "content_filter" in message or "content policy" in message:
            return ProviderContentFilterError(str(exc))
        return ProviderInvalidRequestError(str(exc))
    if isinstance(exc, openai.APIConnectionError | openai.InternalServerError):
        return ProviderUnavailableError(str(exc))
    if isinstance(exc, openai.APIError):
        return ProviderError(str(exc))
    return ProviderUnavailableError(str(exc))


class OpenAIProviderAdapter:
    """Implements `ProviderAdapter` (structural typing — no explicit
    inheritance needed) against `openai.AsyncOpenAI`.
    """

    def __init__(
        self,
        *,
        api_key: str = "",
        base_url: str | None = None,
        max_retries: int = 3,
        base_delay_seconds: float = 0.5,
        max_delay_seconds: float = 8.0,
        client: AsyncOpenAI | None = None,
    ) -> None:
        # `client` is injectable so unit tests exercise the real retry/
        # error-translation logic against a fake without ever
        # constructing a real `AsyncOpenAI` (CLAUDE.md §11: "Dependency-
        # injected clients ... are mockable via shared fakes"). Production
        # code always goes through `get_provider_adapter`, which never
        # passes `client` and always supplies a real `api_key`.
        #
        # The SDK's own retries are disabled (max_retries=0): the bounded
        # backoff below is the *single* retry policy in this codebase,
        # not layered on top of a second, opaque one inside the SDK.
        self._client = client or AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0)
        self._max_retries = max_retries
        self._base_delay_seconds = base_delay_seconds
        self._max_delay_seconds = max_delay_seconds

    async def _retry_rate_limits(self, call: Callable[[], Awaitable[T]]) -> T:
        """Bounded exponential backoff with jitter, on 429s only. Any other
        provider error is translated and re-raised immediately — retrying
        a bad request or an auth failure would never succeed differently.
        """
        attempt = 0
        while True:
            try:
                return await call()
            except openai.RateLimitError as exc:
                attempt += 1
                if attempt > self._max_retries:
                    raise _translate_openai_error(exc) from exc
                delay = min(
                    self._base_delay_seconds * (2 ** (attempt - 1)),
                    self._max_delay_seconds,
                )
                delay += random.uniform(0, delay * 0.25)
                await asyncio.sleep(delay)
            except Exception as exc:
                raise _translate_openai_error(exc) from exc

    def _to_openai_messages(self, request: ChatRequest) -> list[dict[str, Any]]:
        return [{"role": m.role, "content": m.content} for m in request.messages]

    async def chat(self, request: ChatRequest) -> ChatResult:
        # Response shape crossing the SDK boundary is deliberately typed
        # `Any` here: it is translated into strongly-typed domain
        # entities (`ChatResult`/`TokenUsage`) within the next few lines,
        # which is where this codebase's real type safety begins.
        async def _call() -> Any:
            kwargs: dict[str, Any] = {
                "model": request.model,
                "messages": self._to_openai_messages(request),
                "max_tokens": request.max_output_tokens,
                "temperature": request.temperature,
            }
            return await self._client.chat.completions.create(**kwargs)

        response = await self._retry_rate_limits(_call)
        choice = response.choices[0]
        if choice.finish_reason == "content_filter":
            raise ProviderContentFilterError("Response withheld by content filter")
        usage = TokenUsage(
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )
        return ChatResult(
            content=choice.message.content or "",
            usage=usage,
            finish_reason=choice.finish_reason,
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        async def _call() -> Any:
            kwargs: dict[str, Any] = {
                "model": request.model,
                "messages": self._to_openai_messages(request),
                "max_tokens": request.max_output_tokens,
                "temperature": request.temperature,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            return await self._client.chat.completions.create(**kwargs)

        try:
            stream = await self._retry_rate_limits(_call)
        except ProviderError as exc:
            yield StreamError(
                code=exc.code,
                message=exc.message,
                retry_after_seconds=getattr(exc, "retry_after_seconds", None),
            )
            return

        usage: TokenUsage | None = None
        finish_reason = "stop"
        try:
            async for chunk in stream:
                if chunk.usage is not None:
                    usage = TokenUsage(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                    )
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.finish_reason == "content_filter":
                    yield StreamError(
                        code="content_filtered",
                        message="Response withheld by content filter",
                    )
                    return
                if choice.finish_reason is not None:
                    finish_reason = choice.finish_reason
                delta_text = choice.delta.content if choice.delta else None
                if delta_text:
                    yield StreamDelta(text=delta_text)
        except Exception as exc:
            translated = _translate_openai_error(exc)
            yield StreamError(
                code=translated.code,
                message=translated.message,
                retry_after_seconds=getattr(translated, "retry_after_seconds", None),
            )
            return

        yield StreamDone(
            finish_reason=finish_reason,
            usage=usage or TokenUsage(prompt_tokens=0, completion_tokens=0),
        )

    async def call_tool(self, request: ToolCallRequestSpec) -> ToolCallResult:
        async def _call() -> Any:
            kwargs: dict[str, Any] = {
                "model": request.model,
                "messages": [{"role": m.role, "content": m.content} for m in request.messages],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters_json_schema,
                        },
                    }
                    for tool in request.tools
                ],
            }
            return await self._client.chat.completions.create(**kwargs)

        response = await self._retry_rate_limits(_call)
        message = response.choices[0].message
        tool_calls = [
            RequestedToolCall(
                id=call.id,
                name=call.function.name,
                arguments_json=call.function.arguments,
            )
            for call in (message.tool_calls or [])
        ]
        usage = TokenUsage(
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )
        return ToolCallResult(content=message.content, tool_calls=tool_calls, usage=usage)

    async def structured_output(self, request: StructuredOutputRequest) -> StructuredOutputResult:
        async def _call() -> Any:
            kwargs: dict[str, Any] = {
                "model": request.model,
                "messages": [{"role": m.role, "content": m.content} for m in request.messages],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.schema_name,
                        "schema": request.json_schema,
                        "strict": True,
                    },
                },
            }
            return await self._client.chat.completions.create(**kwargs)

        response = await self._retry_rate_limits(_call)
        choice = response.choices[0]
        data = json.loads(choice.message.content or "{}")
        usage = TokenUsage(
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )
        return StructuredOutputResult(data=data, usage=usage)
