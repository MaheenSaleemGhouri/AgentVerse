"""Composition root for this bounded context — the router depends on
these factories, never constructs `OpenAIProviderAdapter` itself
(CLAUDE.md §5: infrastructure implements domain-defined ports, wired at
the edge).
"""

from __future__ import annotations

from functools import lru_cache

from redis.asyncio import from_url as redis_from_url

from agentverse_api.infrastructure.config import get_settings
from agentverse_api.orchestration_service.application.provider_test_service import (
    ProviderTestService,
)
from agentverse_api.orchestration_service.domain.ports.provider_adapter import ProviderAdapter
from agentverse_api.orchestration_service.infrastructure.providers.openai_adapter import (
    OpenAIProviderAdapter,
)
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)


@lru_cache
def get_provider_adapter() -> ProviderAdapter:
    """Process-wide singleton, same rationale as `get_settings`/`get_engine`:
    the underlying `AsyncOpenAI` client owns its own connection pool and
    should not be reconstructed per request.
    """
    settings = get_settings()
    return OpenAIProviderAdapter(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


def get_provider_test_service() -> ProviderTestService:
    return ProviderTestService(adapter=get_provider_adapter())


@lru_cache
def get_job_queue_producer() -> JobQueueProducer:
    """Process-wide singleton — the Redis client owns its own connection
    pool, same rationale as `get_provider_adapter`.
    """
    settings = get_settings()
    redis_client = redis_from_url(  # type: ignore[no-untyped-call]  # redis-py's own stub is untyped here
        settings.redis_url, decode_responses=True
    )
    return JobQueueProducer(redis_client, stream=settings.queue_stream)
