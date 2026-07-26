"""Create-agent use case — thin orchestration over the repository
(CLAUDE.md §7: a route never calls a repository directly). An agent
without at least one version can never be run, so agent + first
version are created together, never as two separate calls a caller
could interleave incorrectly.
"""

from __future__ import annotations

from agentverse_api.orchestration_service.domain.agent_entities import (
    Agent,
    AgentConfig,
    AgentVersion,
)
from agentverse_api.orchestration_service.domain.ports.agent_repository import AgentRepository


async def create_agent(
    *,
    workspace_id: str,
    name: str,
    description: str | None,
    created_by_user_id: str,
    config: AgentConfig,
    agent_repo: AgentRepository,
) -> tuple[Agent, AgentVersion]:
    return await agent_repo.create_agent(
        workspace_id=workspace_id,
        name=name,
        description=description,
        created_by_user_id=created_by_user_id,
        initial_config=config,
    )
