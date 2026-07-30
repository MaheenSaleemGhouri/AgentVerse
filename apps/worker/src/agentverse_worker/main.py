"""ASGI entrypoint: `uvicorn agentverse_worker.main:app`.

See `interface/__init__.py` for why a background-job service runs an
ASGI app in this phase. The FastAPI `lifespan` below is this service's
composition root: it starts the consumer loop as a background task on
startup and cancels it on shutdown so in-flight processing drains
rather than being dropped. The queue/Redis client themselves are built
by `interface.dependencies` so the same singletons back both the
consumer loop and the `/internal/queue/metrics`/`/ready` routes.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from openai import AsyncOpenAI

from agents import set_default_openai_client, set_tracing_disabled
from agentverse_worker.infrastructure.config import get_settings
from agentverse_worker.infrastructure.logging import configure_logging
from agentverse_worker.interface.dependencies import get_queue, get_redis_client
from agentverse_worker.interface.routes.health import router as health_router
from agentverse_worker.interface.routes.metrics import router as metrics_router
from agentverse_worker.interface.routes.queue_metrics import router as queue_metrics_router
from agentverse_worker.mcp.health_sweep import build_health_sweeper
from agentverse_worker.mcp.metrics_aggregation import build_tool_metrics_aggregator
from agentverse_worker.queue.factory import build_queue  # noqa: F401 - re-exported for tests

__all__ = ["app", "build_queue", "create_app", "lifespan"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    redis_client = get_redis_client()
    queue = get_queue()
    await queue.ensure_group()

    consumer_task = asyncio.create_task(queue.run_forever())

    # Second and third background tasks, same shutdown discipline as the
    # queue consumer above: cancelled and awaited, never just dropped, so
    # a cycle mid-flight does not leave a DB session dangling on redeploy.
    sweeper = build_health_sweeper(redis_client, get_settings())
    sweep_task = asyncio.create_task(sweeper.run_forever())

    aggregator = build_tool_metrics_aggregator(redis_client, get_settings())
    aggregation_task = asyncio.create_task(aggregator.run_forever())

    try:
        yield
    finally:
        queue.stop()
        consumer_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await consumer_task
        sweeper.stop()
        sweep_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweep_task
        aggregator.stop()
        aggregation_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await aggregation_task
        await redis_client.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    # AgentVerse translates the SDK's own trace spans into its own
    # trace-event schema (CLAUDE.md §9) — the frontend must never depend
    # on SDK-internal trace formats, so the SDK's own OpenAI-platform
    # tracing export is disabled outright, not merely left unauthenticated.
    set_tracing_disabled(True)
    set_default_openai_client(
        AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url),
        use_for_tracing=False,
    )

    app = FastAPI(
        title="AgentVerse Worker",
        version="0.1.0-alpha",
        openapi_url="/openapi.json" if settings.environment != "production" else None,
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(queue_metrics_router)
    app.include_router(metrics_router)
    return app


app = create_app()
