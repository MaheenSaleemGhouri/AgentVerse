"""Provider-facing domain entities — plain dataclasses, zero framework or
vendor SDK imports (CLAUDE.md Rule 16: no route/workflow/orchestration
code may import a provider SDK; the same discipline applies here — this
module must not import `openai` either, so the shape stays provider-
neutral and a second adapter in Phase 11 never forces a rewrite here).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# Re-exported, not redefined: apps/worker's executor needs the identical
# TokenUsage/cost calculation apps/api uses (Phase 4), so it now lives in
# the shared package (CLAUDE.md §7) — every existing import of
# `agentverse_api...domain.entities.TokenUsage` keeps working unchanged.
from agentverse_shared.cost_accounting import TokenUsage

Role = Literal["system", "user", "assistant", "tool"]

__all__ = [
    "ChatMessage",
    "ChatRequest",
    "ChatResult",
    "RequestedToolCall",
    "Role",
    "StreamDelta",
    "StreamDone",
    "StreamError",
    "StreamEvent",
    "StructuredOutputRequest",
    "StructuredOutputResult",
    "TokenUsage",
    "ToolCallRequestSpec",
    "ToolCallResult",
    "ToolSchema",
]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class ChatRequest:
    model: str
    messages: list[ChatMessage]
    max_output_tokens: int | None = None
    temperature: float | None = None


@dataclass(frozen=True, slots=True)
class ChatResult:
    content: str
    usage: TokenUsage
    finish_reason: str


@dataclass(frozen=True, slots=True)
class StreamDelta:
    """One incremental token/text fragment."""

    text: str


@dataclass(frozen=True, slots=True)
class StreamDone:
    """Terminal event: the stream completed successfully."""

    finish_reason: str
    usage: TokenUsage


@dataclass(frozen=True, slots=True)
class StreamError:
    """Terminal event: the stream ended in a provider error.

    Carries the same `code` taxonomy as `domain.provider_errors` so a
    consumer never has to catch an exception out of an async generator —
    the error is a value, matching the streaming-event shape this
    interface is deliberately built around instead of the OpenAI SDK's.
    """

    code: str
    message: str
    retry_after_seconds: float | None = None


StreamEvent = StreamDelta | StreamDone | StreamError


@dataclass(frozen=True, slots=True)
class ToolSchema:
    name: str
    description: str
    parameters_json_schema: dict[str, object]


@dataclass(frozen=True, slots=True)
class ToolCallRequestSpec:
    """Request to let the model decide whether to call one of `tools`.

    This is the provider-level capability only — it returns the model's
    *decision*, never executes anything. Execution always routes through
    AgentVerse's central tool-execution boundary (Phase 6), which is out
    of scope here.
    """

    model: str
    messages: list[ChatMessage]
    tools: list[ToolSchema]


@dataclass(frozen=True, slots=True)
class RequestedToolCall:
    id: str
    name: str
    arguments_json: str


@dataclass(frozen=True, slots=True)
class ToolCallResult:
    content: str | None
    tool_calls: list[RequestedToolCall] = field(default_factory=list)
    usage: TokenUsage | None = None


@dataclass(frozen=True, slots=True)
class StructuredOutputRequest:
    model: str
    messages: list[ChatMessage]
    json_schema: dict[str, object]
    schema_name: str


@dataclass(frozen=True, slots=True)
class StructuredOutputResult:
    data: dict[str, object]
    usage: TokenUsage
