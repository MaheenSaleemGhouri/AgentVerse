"""Adapter binding `AgentImporter` to the orchestration context.

This file is the *only* place the marketplace touches orchestration, and
it does so through that context's own use case rather than its tables.
Rule 5 forbids one context reading or writing another's schema; a direct
`INSERT INTO agents` here would work today and quietly become the reason
the two can never be split.

It lives in `infrastructure/` for the same reason a Postgres adapter
does: from the marketplace's point of view, orchestration is an external
system it depends on through a port, and the concrete binding belongs at
the edge.
"""

from __future__ import annotations

from agentverse_api.marketplace_service.domain.install import ImportedConfig
from agentverse_api.orchestration_service.application.create_agent import create_agent
from agentverse_api.orchestration_service.domain.agent_entities import AgentConfig
from agentverse_api.orchestration_service.domain.ports.agent_repository import AgentRepository


class OrchestrationAgentImporter:
    """Implements `domain.ports.AgentImporter`."""

    def __init__(self, agents: AgentRepository) -> None:
        self._agents = agents

    async def create_from_listing(
        self,
        *,
        workspace_id: str,
        name: str,
        description: str,
        created_by_user_id: str,
        config: ImportedConfig,
    ) -> str:
        agent, _version = await create_agent(
            workspace_id=workspace_id,
            name=name,
            description=description,
            created_by_user_id=created_by_user_id,
            config=AgentConfig(
                model=config.model,
                system_instructions=config.system_instructions,
                temperature=config.temperature,
                max_output_tokens=config.max_output_tokens,
                tools=list(config.tools),
                # Empty, always. The snapshot's knowledge bases belonged
                # to the publisher's workspace; `sanitize_config` drops
                # them, and this is the second place that stays true.
                knowledge_base_ids=[],
            ),
            agent_repo=self._agents,
        )
        return agent.id

    async def exists(self, *, workspace_id: str, agent_id: str) -> bool:
        return (
            await self._agents.get_agent(workspace_id=workspace_id, agent_id=agent_id) is not None
        )
