"""The `ProviderAdapter` port (CLAUDE.md Rule 16): the *only* interface
any orchestration, route, or workflow code is ever allowed to depend on
for LLM calls. `infrastructure/providers/openai_adapter.py` implements
this against the OpenAI SDK; a second provider (Phase 11) implements the
same four methods with zero changes required here or in any caller.

Shaped around AgentVerse's own error taxonomy and streaming-event union
(`domain.provider_errors`, `domain.entities.StreamEvent`) rather than the
OpenAI SDK's types — the risk this phase's roadmap entry names explicitly
(an OpenAI-shaped interface would force a breaking change the moment a
second provider arrives).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from agentverse_api.orchestration_service.domain.entities import (
    ChatRequest,
    ChatResult,
    StreamEvent,
    StructuredOutputRequest,
    StructuredOutputResult,
    ToolCallRequestSpec,
    ToolCallResult,
)


class ProviderAdapter(Protocol):
    async def chat(self, request: ChatRequest) -> ChatResult:
        """Single non-streaming completion."""
        ...

    def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        """Streaming completion. Terminates with exactly one `StreamDone`
        or `StreamError` — never both, never neither."""
        ...

    async def call_tool(self, request: ToolCallRequestSpec) -> ToolCallResult:
        """Let the model decide whether to call one of `request.tools`.

        Returns the model's decision only. Never executes a tool call —
        that always goes through the central tool-execution boundary
        (Phase 6), which is out of scope for this port.
        """
        ...

    async def structured_output(self, request: StructuredOutputRequest) -> StructuredOutputResult:
        """A completion constrained to `request.json_schema` via the
        provider's native structured-output mode (never prompt-only
        JSON coaxing, per CLAUDE.md §9 OpenAI integration)."""
        ...
