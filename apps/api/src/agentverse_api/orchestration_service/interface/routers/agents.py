"""`/api/v1/workspaces/{workspace_id}/agents` — agent CRUD and run
submission (CLAUDE.md §7 REST conventions: resources nested under their
workspace in the URL).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_member,
    require_viewer,
)
from agentverse_api.orchestration_service.application.create_agent import create_agent
from agentverse_api.orchestration_service.application.run_agent import LockFactory, run_agent
from agentverse_api.orchestration_service.domain.agent_entities import (
    Agent,
    AgentConfig,
    AgentVersion,
)
from agentverse_api.orchestration_service.domain.ports.agent_repository import AgentRepository
from agentverse_api.orchestration_service.domain.ports.run_repository import AgentRunRepository
from agentverse_api.orchestration_service.domain.run_exceptions import (
    AgentNotRunnableError,
    RunSubmissionConflictError,
)
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_agent_repository,
    get_agent_run_repository,
    get_job_queue_producer,
    get_lock_factory,
)
from agentverse_api.orchestration_service.interface.schemas.agents import (
    AgentResponse,
    AgentVersionResponse,
    CreateAgentRequest,
    CreateAgentResponse,
    RunAgentRequest,
    RunResponse,
    UpdateAgentVersionRequest,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/agents", tags=["agents"])


def _agent_response(agent: Agent) -> AgentResponse:
    return AgentResponse(
        id=agent.id,
        workspace_id=agent.workspace_id,
        name=agent.name,
        description=agent.description,
        status=agent.status.value,
        published_version_id=agent.published_version_id,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


@router.post("", response_model=CreateAgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_route(
    body: CreateAgentRequest,
    context: WorkspaceContext = Depends(require_member),
    agent_repo: AgentRepository = Depends(get_agent_repository),
) -> CreateAgentResponse:
    config = AgentConfig(
        model=body.model,
        system_instructions=body.system_instructions,
        temperature=body.temperature,
        max_output_tokens=body.max_output_tokens,
        tools=body.tools,
        knowledge_base_ids=body.knowledge_base_ids,
    )
    agent, version = await create_agent(
        workspace_id=context.workspace_id,
        name=body.name,
        description=body.description,
        created_by_user_id=context.user_id,
        config=config,
        agent_repo=agent_repo,
    )
    return CreateAgentResponse(
        agent=_agent_response(agent),
        version=_version_response(version),
    )


@router.get("", response_model=list[AgentResponse])
async def list_agents_route(
    context: WorkspaceContext = Depends(require_viewer),
    agent_repo: AgentRepository = Depends(get_agent_repository),
) -> list[AgentResponse]:
    agents = await agent_repo.list_agents(workspace_id=context.workspace_id)
    return [_agent_response(a) for a in agents]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent_route(
    agent_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    agent_repo: AgentRepository = Depends(get_agent_repository),
) -> AgentResponse:
    agent = await agent_repo.get_agent(workspace_id=context.workspace_id, agent_id=agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return _agent_response(agent)


def _version_response(version: AgentVersion) -> AgentVersionResponse:
    return AgentVersionResponse(
        id=version.id,
        version_number=version.version_number,
        model=version.config.model,
        system_instructions=version.config.system_instructions,
        temperature=version.config.temperature,
        max_output_tokens=version.config.max_output_tokens,
        tools=version.config.tools,
        knowledge_base_ids=version.config.knowledge_base_ids,
        created_at=version.created_at,
    )


@router.get("/{agent_id}/versions/latest", response_model=AgentVersionResponse)
async def get_latest_version_route(
    agent_id: str,
    context: WorkspaceContext = Depends(require_viewer),
    agent_repo: AgentRepository = Depends(get_agent_repository),
) -> AgentVersionResponse:
    agent = await agent_repo.get_agent(workspace_id=context.workspace_id, agent_id=agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    latest = await agent_repo.get_latest_version(agent_id=agent_id)
    if latest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent has no version")
    return _version_response(latest)


@router.post(
    "/{agent_id}/versions", response_model=AgentVersionResponse, status_code=status.HTTP_201_CREATED
)
async def create_version_route(
    agent_id: str,
    body: UpdateAgentVersionRequest,
    context: WorkspaceContext = Depends(require_member),
    agent_repo: AgentRepository = Depends(get_agent_repository),
) -> AgentVersionResponse:
    agent = await agent_repo.get_agent(workspace_id=context.workspace_id, agent_id=agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    config = AgentConfig(
        model=body.model,
        system_instructions=body.system_instructions,
        temperature=body.temperature,
        max_output_tokens=body.max_output_tokens,
        tools=body.tools,
        knowledge_base_ids=body.knowledge_base_ids,
    )
    version = await agent_repo.create_version(
        agent_id=agent_id, config=config, created_by_user_id=context.user_id
    )
    return _version_response(version)


@router.post("/{agent_id}/publish", response_model=AgentResponse)
async def publish_agent_route(
    agent_id: str,
    context: WorkspaceContext = Depends(require_member),
    agent_repo: AgentRepository = Depends(get_agent_repository),
) -> AgentResponse:
    agent = await agent_repo.get_agent(workspace_id=context.workspace_id, agent_id=agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    latest = await agent_repo.get_latest_version(agent_id=agent_id)
    if latest is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent has no version")
    published = await agent_repo.publish_version(agent_id=agent_id, version_id=latest.id)
    return _agent_response(published)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_agent_route(
    agent_id: str,
    context: WorkspaceContext = Depends(require_member),
    agent_repo: AgentRepository = Depends(get_agent_repository),
) -> None:
    await agent_repo.soft_delete(workspace_id=context.workspace_id, agent_id=agent_id)


@router.post("/{agent_id}/runs", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_run_route(
    agent_id: str,
    body: RunAgentRequest,
    context: WorkspaceContext = Depends(require_member),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    agent_repo: AgentRepository = Depends(get_agent_repository),
    run_repo: AgentRunRepository = Depends(get_agent_run_repository),
    producer: JobQueueProducer = Depends(get_job_queue_producer),
    lock_factory: LockFactory = Depends(get_lock_factory),
) -> RunResponse:
    try:
        run = await run_agent(
            workspace_id=context.workspace_id,
            agent_id=agent_id,
            input=body.input,
            idempotency_key=idempotency_key,
            agent_repo=agent_repo,
            run_repo=run_repo,
            producer=producer,
            lock_factory=lock_factory,
        )
    except AgentNotRunnableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Agent has no published version to run",
        ) from exc
    except RunSubmissionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not confirm run submission — retry with the same Idempotency-Key",
        ) from exc

    return RunResponse(
        id=run.id,
        agent_id=run.agent_id,
        status=run.status.value,
        idempotency_key=run.idempotency_key,
        cost_micro_usd=run.cost_micro_usd,
        error_message=run.error_message,
        created_at=run.created_at,
    )
