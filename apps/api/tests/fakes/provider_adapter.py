"""In-memory `ProviderAdapter` fake — used by unit/route tests so
application-layer logic is tested without a real OpenAI call
(CLAUDE.md §11).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from agentverse_api.orchestration_service.domain.entities import (
    ChatRequest,
    ChatResult,
    StreamEvent,
    StructuredOutputRequest,
    StructuredOutputResult,
    TokenUsage,
    ToolCallRequestSpec,
    ToolCallResult,
)


@dataclass
class FakeProviderAdapter:
    """Replays a fixed, injected sequence of `StreamEvent`s for
    `stream_chat`. Records every request it was called with so tests can
    assert on what was sent, not just what came back.
    """

    stream_events: list[StreamEvent] = field(default_factory=list)
    chat_result: ChatResult | None = None
    tool_call_result: ToolCallResult | None = None
    structured_output_result: StructuredOutputResult | None = None
    requests: list[ChatRequest] = field(default_factory=list)

    async def chat(self, request: ChatRequest) -> ChatResult:
        self.requests.append(request)
        if self.chat_result is None:
            return ChatResult(
                content="fake response",
                usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
                finish_reason="stop",
            )
        return self.chat_result

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        self.requests.append(request)
        for event in self.stream_events:
            yield event

    async def call_tool(self, request: ToolCallRequestSpec) -> ToolCallResult:
        if self.tool_call_result is None:
            return ToolCallResult(content="fake response")
        return self.tool_call_result

    async def structured_output(self, request: StructuredOutputRequest) -> StructuredOutputResult:
        if self.structured_output_result is None:
            return StructuredOutputResult(
                data={}, usage=TokenUsage(prompt_tokens=1, completion_tokens=1)
            )
        return self.structured_output_result
