"""Composition root for this bounded context — the router depends on
these factories, never constructs `OpenAIProviderAdapter` itself
(CLAUDE.md §5: infrastructure implements domain-defined ports, wired at
the edge).
"""

from __future__ import annotations

from functools import lru_cache

import httpx
from agentverse_shared.embeddings.openai_provider import OpenAIEmbeddingProvider
from agentverse_shared.embeddings.port import EmbeddingProvider
from agentverse_shared.locks.distributed_lock import DistributedLock
from agentverse_shared.retrieval.port import ChunkSearchPort
from agentverse_shared.retrieval.postgres_search import PostgresChunkSearch
from agentverse_shared.security.envelope import CredentialVault, KeyRing
from agentverse_shared.storage.document_store import DocumentStore, build_document_store
from agentverse_shared.text.tokenizer import TiktokenCounter, TokenCounter
from fastapi import Depends
from redis.asyncio import Redis
from redis.asyncio import from_url as redis_from_url
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.infrastructure.config import get_settings
from agentverse_api.infrastructure.db import get_db_session
from agentverse_api.orchestration_service.application.oauth_flow import OAuthFlowService
from agentverse_api.orchestration_service.application.provider_test_service import (
    ProviderTestService,
)
from agentverse_api.orchestration_service.application.run_agent import LockFactory
from agentverse_api.orchestration_service.domain.ports.agent_repository import AgentRepository
from agentverse_api.orchestration_service.domain.ports.integration_repository import (
    IntegrationRepository,
)
from agentverse_api.orchestration_service.domain.ports.knowledge_repository import (
    KnowledgeRepository,
)
from agentverse_api.orchestration_service.domain.ports.provider_adapter import ProviderAdapter
from agentverse_api.orchestration_service.domain.ports.run_repository import AgentRunRepository
from agentverse_api.orchestration_service.domain.ports.team_repository import TeamRepository
from agentverse_api.orchestration_service.domain.ports.workflow_repository import (
    WorkflowRepository,
)
from agentverse_api.orchestration_service.domain.ports.workflow_run_repository import (
    WorkflowRunRepository,
)
from agentverse_api.orchestration_service.infrastructure.integration_repository import (
    SqlIntegrationRepository,
)
from agentverse_api.orchestration_service.infrastructure.knowledge_repository import (
    SqlKnowledgeRepository,
)
from agentverse_api.orchestration_service.infrastructure.oauth.providers import (
    build_oauth_providers,
)
from agentverse_api.orchestration_service.infrastructure.providers.anthropic_adapter import (
    AnthropicProviderAdapter,
)
from agentverse_api.orchestration_service.infrastructure.providers.multi_provider_adapter import (
    MultiProviderAdapter,
)
from agentverse_api.orchestration_service.infrastructure.providers.openai_adapter import (
    OpenAIProviderAdapter,
)
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)
from agentverse_api.orchestration_service.infrastructure.repositories import (
    SqlAgentRepository,
    SqlAgentRunRepository,
)
from agentverse_api.orchestration_service.infrastructure.team_repository import (
    SqlTeamRepository,
)
from agentverse_api.orchestration_service.infrastructure.workflow_repository import (
    SqlWorkflowRepository,
)
from agentverse_api.orchestration_service.infrastructure.workflow_run_repository import (
    SqlWorkflowRunRepository,
)


@lru_cache
def get_provider_adapter() -> ProviderAdapter:
    """Process-wide singleton, same rationale as `get_settings`/`get_engine`:
    the underlying SDK clients own their own connection pools and should
    not be reconstructed per request.

    Returns a `MultiProviderAdapter` so both current consumers
    (`ProviderTestService`, `AssistantService`) can address either
    provider by an `anthropic/`-prefixed model string with zero changes
    to either — Anthropic is wired in only when configured; an
    unconfigured deployment behaves exactly as before Phase 11.
    """
    settings = get_settings()
    openai_adapter = OpenAIProviderAdapter(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )
    # Narrowed via a direct `is not None` check (not the `anthropic_configured`
    # property) so mypy sees `settings.anthropic_api_key` as `str` here.
    anthropic_adapter = (
        AnthropicProviderAdapter(api_key=settings.anthropic_api_key)
        if settings.anthropic_api_key is not None
        else None
    )
    return MultiProviderAdapter(openai=openai_adapter, anthropic=anthropic_adapter)


def get_provider_test_service() -> ProviderTestService:
    return ProviderTestService(adapter=get_provider_adapter())


@lru_cache
def get_redis_client() -> Redis:
    """Process-wide singleton — shared by the job-queue producer and the
    distributed-lock factory, so there is exactly one connection pool
    per process, not one per consumer (same rationale as apps/worker's
    `interface.dependencies.get_redis_client`).
    """
    settings = get_settings()
    return redis_from_url(  # type: ignore[no-untyped-call,no-any-return]  # redis-py's own stub is untyped here
        settings.redis_url, decode_responses=True
    )


@lru_cache
def get_job_queue_producer() -> JobQueueProducer:
    settings = get_settings()
    return JobQueueProducer(get_redis_client(), stream=settings.queue_stream)


def get_lock_factory() -> LockFactory:
    """Returns a factory, not a single lock: `run_agent` needs a fresh
    `DistributedLock` per idempotency key, not one shared instance.
    """
    redis_client = get_redis_client()

    def _factory(key: str) -> DistributedLock:
        return DistributedLock(redis_client, key, ttl_ms=30_000)

    return _factory


def get_agent_repository(session: AsyncSession = Depends(get_db_session)) -> AgentRepository:
    return SqlAgentRepository(session)


def get_agent_run_repository(
    session: AsyncSession = Depends(get_db_session),
) -> AgentRunRepository:
    return SqlAgentRunRepository(session)


def get_team_repository(session: AsyncSession = Depends(get_db_session)) -> TeamRepository:
    return SqlTeamRepository(session)


def get_workflow_repository(
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowRepository:
    return SqlWorkflowRepository(session)


def get_workflow_run_repository(
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowRunRepository:
    return SqlWorkflowRunRepository(session)


def get_integration_repository(
    session: AsyncSession = Depends(get_db_session),
) -> IntegrationRepository:
    return SqlIntegrationRepository(session)


@lru_cache
def get_credential_vault() -> CredentialVault:
    """Process-wide singleton, same rationale as the provider adapter.

    The key ring is read from the environment at construction, so a
    missing key fails here — at startup, loudly — rather than on the
    first credential write of the first user who tries one
    (CLAUDE.md Rule 1).
    """
    return CredentialVault(KeyRing.from_env())


def get_knowledge_repository(
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeRepository:
    return SqlKnowledgeRepository(session)


def get_chunk_search(session: AsyncSession = Depends(get_db_session)) -> ChunkSearchPort:
    return PostgresChunkSearch(session)


@lru_cache
def get_document_store() -> DocumentStore:
    """Process-wide singleton.

    apps/worker constructs the same kind of store under its own,
    identically-named settings. The two services share the key *layout*
    and the bucket/root as a contract, never a config object
    (CLAUDE.md §5). S3 is chosen whenever a bucket is configured — the
    two services run as separate containers with no shared filesystem,
    so `LocalDocumentStore` is reachable by whichever service wrote to
    it and no other; it survives here only for single-container/local
    dev where that's not a problem.
    """
    settings = get_settings()
    return build_document_store(
        root=settings.document_storage_root,
        bucket=settings.document_storage_bucket,
        endpoint_url=settings.document_storage_endpoint_url,
        region=settings.document_storage_region,
        access_key_id=settings.document_storage_access_key_id,
        secret_access_key=settings.document_storage_secret_access_key,
    )


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    """The single adapter every embedding call goes through (Rule 16).
    Cached for the same reason as the chat provider: the underlying
    client owns a connection pool.
    """
    settings = get_settings()
    return OpenAIEmbeddingProvider(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
        model_version=settings.embedding_model_version,
        base_url=settings.openai_base_url,
    )


@lru_cache
def get_token_counter() -> TokenCounter:
    """Cached because the first `count` call loads (and network-fetches)
    the BPE encoding — that must not happen per request.
    """
    return TiktokenCounter()


@lru_cache
def get_oauth_http_client() -> httpx.AsyncClient:
    """Process-wide singleton, same rationale as the provider adapter and
    Redis client — this is a connection pool, not per-request state.

    Points only at each provider's own token endpoint (a fixed, known
    host from the registry in `oauth.providers`, never a user-supplied
    URL), so this does not need the agent-tool-call egress guard —
    that guard exists for outbound calls whose destination an attacker
    influences, which this is not.
    """
    return httpx.AsyncClient()


def get_oauth_flow_service(
    repo: IntegrationRepository = Depends(get_integration_repository),
    vault: CredentialVault = Depends(get_credential_vault),
) -> OAuthFlowService:
    settings = get_settings()
    return OAuthFlowService(
        repo=repo,
        vault=vault,
        providers=build_oauth_providers(settings),
        callback_url=f"{settings.api_public_url}/api/v1/integrations/oauth/callback",
        http_client=get_oauth_http_client(),
    )
