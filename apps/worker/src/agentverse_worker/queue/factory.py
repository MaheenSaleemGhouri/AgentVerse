"""Composition wiring for `RedisStreamQueue`, factored out of `main.py`
so both the ASGI lifespan and interface-layer dependencies can
construct/share it without a circular import.
"""

from __future__ import annotations

import uuid

from agentverse_shared.embeddings.openai_provider import OpenAIEmbeddingProvider
from agentverse_shared.retrieval.postgres_search import PostgresChunkSearch
from agentverse_shared.security.envelope import CredentialVault, KeyRing
from agentverse_shared.storage.document_store import build_document_store
from agentverse_shared.text.tokenizer import TiktokenCounter
from redis.asyncio import Redis

from agentverse_worker.agents.repository import WorkerAgentRepository
from agentverse_worker.infrastructure.config import Settings
from agentverse_worker.infrastructure.db import get_session, get_session_factory
from agentverse_worker.jobs.agent_run_job import handle_agent_run_job
from agentverse_worker.jobs.echo_job import handle_echo_job
from agentverse_worker.jobs.kb_ingest_job import handle_kb_ingest_job
from agentverse_worker.jobs.team_session_job import handle_team_session_job
from agentverse_worker.jobs.workflow_node_job import WorkflowExecutionDeps, handle_workflow_node_job
from agentverse_worker.knowledge.directory import WorkerKnowledgeBaseDirectory
from agentverse_worker.knowledge.repository import WorkerKnowledgeRepository
from agentverse_worker.mcp.repository import WorkerIntegrationRepository
from agentverse_worker.queue.models import Job, JobHandler, JobResult
from agentverse_worker.queue.redis_stream_queue import RedisStreamQueue
from agentverse_worker.teams.repository import WorkerTeamRepository
from agentverse_worker.workflows.repository import WorkerWorkflowRepository


def build_queue(redis_client: Redis, settings: Settings) -> RedisStreamQueue:
    """Callable directly in tests with a fake Redis client and custom
    `Settings` (e.g. tiny retry delays) — CLAUDE.md §11.

    `settings.worker_pool` selects which stream *this instance*
    consumes (docs/adr/0018) — `"priority"` binds to the
    dedicated-infrastructure stream/group, `"shared"` (the default)
    binds to the same stream/group every worker instance has always
    used. Same handler dict either way: a priority-pool instance runs
    the identical code, just against a different stream.
    """
    is_priority = settings.worker_pool == "priority"
    stream = settings.queue_stream_priority if is_priority else settings.queue_stream
    dlq_stream = settings.queue_dlq_stream_priority if is_priority else settings.queue_dlq_stream
    group = settings.queue_group_priority if is_priority else settings.queue_group

    # Built once per queue, not per job: the tokenizer's encoding load is
    # expensive and the embedding client owns a connection pool. Shared
    # by ingestion and by run-time grounding — the same embedder that
    # wrote a KB's vectors must also embed the queries searching them.
    counter = TiktokenCounter()
    embedder = OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
        model_version=settings.embedding_model_version,
        base_url=settings.openai_base_url,
    )
    store = build_document_store(
        root=settings.document_storage_root,
        bucket=settings.document_storage_bucket,
        endpoint_url=settings.document_storage_endpoint_url,
        region=settings.document_storage_region,
        access_key_id=settings.document_storage_access_key_id,
        secret_access_key=settings.document_storage_secret_access_key,
    )

    # Built once, like the embedder: the key ring is read from the
    # environment at construction and a missing key must fail here — at
    # startup, loudly — rather than on the first tool call of the first
    # run that happens to need a credential.
    vault = CredentialVault(KeyRing.from_env())

    async def _agent_run_handler(job: Job) -> JobResult:
        # Closure over `settings`/`redis_client` to match the single-arg
        # `JobHandler` shape the queue calls. Opens one DB session for
        # this job's duration — `handle_agent_run_job` itself takes its
        # collaborators explicitly so it stays directly unit-testable
        # with fakes, without going through a real session at all.
        async with get_session() as session:
            return await handle_agent_run_job(
                job,
                settings=settings,
                redis=redis_client,
                repo=WorkerAgentRepository(session),
                directory=WorkerKnowledgeBaseDirectory(session),
                search=PostgresChunkSearch(session),
                embedder=embedder,
                counter=counter,
                integrations=WorkerIntegrationRepository(session, vault),
            )

    async def _kb_ingest_handler(job: Job) -> JobResult:
        async with get_session() as session:
            repo = WorkerKnowledgeRepository(session)
            return await handle_kb_ingest_job(
                job, repo=repo, store=store, embedder=embedder, counter=counter
            )

    async def _team_session_handler(job: Job) -> JobResult:
        # Two distinct session lifetimes here, and the distinction
        # matters: the outer one is the job's own unit of work (status
        # transitions, trace writes), while `get_session_factory()` is
        # handed down so shared memory and the SDK `Session` can open
        # their own short transactions per call — neither may hold a
        # connection open across an LLM call (CLAUDE.md §7).
        async with get_session() as session:
            return await handle_team_session_job(
                job,
                redis=redis_client,
                repo=WorkerTeamRepository(session),
                session_factory=get_session_factory(),
            )

    async def _workflow_node_handler(job: Job) -> JobResult:
        # A single session for this job's own reads/writes (workflow_
        # runs/workflow_node_runs, agent_runs, team_sessions) — the
        # in-process sub-run/sub-session it calls into opens its own
        # short transactions via `get_session_factory()`, never sharing
        # this one across an LLM call (CLAUDE.md §7).
        async with get_session() as session:
            deps = WorkflowExecutionDeps(
                settings=settings,
                redis=redis_client,
                # The stream *this instance* consumes from, not
                # unconditionally the default — a workflow node running
                # on the priority pool must re-enqueue its follow-on
                # node onto the priority stream too, or a multi-node
                # workflow would silently fall back to the shared queue
                # after its first node.
                queue_stream=stream,
                workflow_repo=WorkerWorkflowRepository(session),
                agent_repo=WorkerAgentRepository(session),
                team_repo=WorkerTeamRepository(session),
                directory=WorkerKnowledgeBaseDirectory(session),
                search=PostgresChunkSearch(session),
                embedder=embedder,
                counter=counter,
                integrations=WorkerIntegrationRepository(session, vault),
                session_factory=get_session_factory(),
            )
            return await handle_workflow_node_job(job, deps=deps)

    handlers: dict[str, JobHandler] = {
        "echo": handle_echo_job,
        "agent_run": _agent_run_handler,
        "kb_ingest": _kb_ingest_handler,
        "team_session": _team_session_handler,
        "workflow_node": _workflow_node_handler,
    }

    return RedisStreamQueue(
        redis_client,
        stream=stream,
        dlq_stream=dlq_stream,
        group=group,
        consumer=f"{settings.service_name}-{uuid.uuid4().hex[:8]}",
        handlers=handlers,
        visibility_timeout_ms=settings.queue_visibility_timeout_ms,
        base_delay_seconds=settings.queue_base_delay_seconds,
        max_delay_seconds=settings.queue_max_delay_seconds,
        block_ms=settings.queue_block_ms,
        batch_size=settings.queue_batch_size,
    )
