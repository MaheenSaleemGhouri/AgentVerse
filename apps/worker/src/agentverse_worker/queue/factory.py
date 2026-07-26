"""Composition wiring for `RedisStreamQueue`, factored out of `main.py`
so both the ASGI lifespan and interface-layer dependencies can
construct/share it without a circular import.
"""

from __future__ import annotations

import uuid

from redis.asyncio import Redis

from agentverse_worker.agents.repository import WorkerAgentRepository
from agentverse_worker.infrastructure.config import Settings
from agentverse_worker.infrastructure.db import get_session
from agentverse_worker.jobs.agent_run_job import handle_agent_run_job
from agentverse_worker.jobs.echo_job import handle_echo_job
from agentverse_worker.queue.models import Job, JobHandler, JobResult
from agentverse_worker.queue.redis_stream_queue import RedisStreamQueue


def build_queue(redis_client: Redis, settings: Settings) -> RedisStreamQueue:
    """Callable directly in tests with a fake Redis client and custom
    `Settings` (e.g. tiny retry delays) — CLAUDE.md §11.
    """

    async def _agent_run_handler(job: Job) -> JobResult:
        # Closure over `settings`/`redis_client` to match the single-arg
        # `JobHandler` shape the queue calls. Opens one DB session for
        # this job's duration — `handle_agent_run_job` itself takes the
        # repository explicitly so it stays directly unit-testable with
        # a fake, without going through a real session at all.
        async with get_session() as session:
            repo = WorkerAgentRepository(session)
            return await handle_agent_run_job(job, settings=settings, redis=redis_client, repo=repo)

    handlers: dict[str, JobHandler] = {"echo": handle_echo_job, "agent_run": _agent_run_handler}

    return RedisStreamQueue(
        redis_client,
        stream=settings.queue_stream,
        dlq_stream=settings.queue_dlq_stream,
        group=settings.queue_group,
        consumer=f"{settings.service_name}-{uuid.uuid4().hex[:8]}",
        handlers=handlers,
        visibility_timeout_ms=settings.queue_visibility_timeout_ms,
        base_delay_seconds=settings.queue_base_delay_seconds,
        max_delay_seconds=settings.queue_max_delay_seconds,
        block_ms=settings.queue_block_ms,
        batch_size=settings.queue_batch_size,
    )
