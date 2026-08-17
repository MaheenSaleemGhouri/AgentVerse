"""Dispatches to one of several concrete `ProviderAdapter` implementations
by inspecting `request.model`, so `ProviderTestService`/`AssistantService`
(`ProviderAdapter`'s only real consumers) never change to support a
second provider — the port's own docstring's promise, kept literally.

Imports no provider SDK itself (only the adapter classes, which already
carry Rule 16's import boundary) — this file is not part of the Rule 16
allowlist check by name, only by directory, and it stays compliant by
construction since it never imports `openai`/`anthropic` directly.

Model-string convention shared with `apps/worker`'s `resolve_model()`:
no `/` prefix means OpenAI (the default, unchanged); an `anthropic/`
prefix means Anthropic. Requesting an Anthropic-prefixed model when no
Anthropic key is configured is a `ProviderInvalidRequestError`, not a
silent fallback to a different provider than the one asked for.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from agentverse_api.orchestration_service.domain.entities import (
    ChatRequest,
    ChatResult,
    StreamError,
    StreamEvent,
    StructuredOutputRequest,
    StructuredOutputResult,
    ToolCallRequestSpec,
    ToolCallResult,
)
from agentverse_api.orchestration_service.domain.ports.provider_adapter import ProviderAdapter
from agentverse_api.orchestration_service.domain.provider_errors import (
    ProviderError,
    ProviderInvalidRequestError,
)

_ANTHROPIC_PREFIX = "anthropic/"


class MultiProviderAdapter:
    """Implements `ProviderAdapter` by routing on `request.model`'s
    provider prefix to one of the wrapped adapters.
    """

    def __init__(self, *, openai: ProviderAdapter, anthropic: ProviderAdapter | None) -> None:
        self._openai = openai
        self._anthropic = anthropic

    def _select(self, model: str) -> ProviderAdapter:
        if not model.startswith(_ANTHROPIC_PREFIX):
            return self._openai
        if self._anthropic is None:
            raise ProviderInvalidRequestError(
                f"Model {model!r} requires Anthropic, which is not configured "
                "on this deployment (AGENTVERSE_API_ANTHROPIC_API_KEY unset)."
            )
        return self._anthropic

    async def chat(self, request: ChatRequest) -> ChatResult:
        return await self._select(request.model).chat(request)

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        # An async generator function (has `yield` below), matching
        # every other `stream_chat` in this codebase: a bad/unconfigured
        # provider terminates in a `StreamError`, never a raised
        # exception out of the async generator — the same "never raise,
        # always terminate in exactly one StreamDone or StreamError"
        # contract the port's docstring requires.
        try:
            adapter = self._select(request.model)
        except ProviderError as exc:
            yield StreamError(code=exc.code, message=exc.message)
            return
        async for event in adapter.stream_chat(request):
            yield event

    async def call_tool(self, request: ToolCallRequestSpec) -> ToolCallResult:
        return await self._select(request.model).call_tool(request)

    async def structured_output(self, request: StructuredOutputRequest) -> StructuredOutputResult:
        return await self._select(request.model).structured_output(request)
