"""Thin use case behind the internal provider-test route — keeps the
router itself free of any LLM-call logic (CLAUDE.md §7: "No LLM/provider
SDK call ... lives inside a route file").
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from agentverse_api.orchestration_service.application.cost_accounting import (
    calculate_cost_micro_usd,
)
from agentverse_api.orchestration_service.application.model_routing import DEFAULT_MODEL
from agentverse_api.orchestration_service.domain.entities import (
    ChatMessage,
    ChatRequest,
    StreamDone,
    StreamEvent,
)
from agentverse_api.orchestration_service.domain.ports.provider_adapter import ProviderAdapter

logger = logging.getLogger(__name__)


class ProviderTestService:
    """Proves `ProviderAdapter.stream_chat` end-to-end. No agent/run/worker
    concept involved — that is deliberately out of this phase's scope.
    """

    def __init__(self, adapter: ProviderAdapter) -> None:
        self._adapter = adapter

    async def stream_completion(
        self, *, prompt: str, model: str | None = None
    ) -> AsyncIterator[StreamEvent]:
        resolved_model = model or DEFAULT_MODEL
        request = ChatRequest(
            model=resolved_model,
            messages=[ChatMessage(role="user", content=prompt)],
        )

        async for event in self._adapter.stream_chat(request):
            if isinstance(event, StreamDone):
                cost_micro_usd = calculate_cost_micro_usd(resolved_model, event.usage)
                logger.info(
                    "provider_test_completion model=%s prompt_tokens=%d "
                    "completion_tokens=%d cost_micro_usd=%d",
                    resolved_model,
                    event.usage.prompt_tokens,
                    event.usage.completion_tokens,
                    cost_micro_usd,
                )
            yield event
