"""Repository port (Protocol). `infrastructure/repositories.py` implements
this against Postgres; tests implement it against an in-memory fake
(CLAUDE.md §5: infrastructure implements domain-defined ports).
"""

from __future__ import annotations

from typing import Protocol

from agentverse_shared.search import SearchMatch

from agentverse_api.orchestration_service.domain.agent_entities import (
    Agent,
    AgentConfig,
    AgentVersion,
)


class AgentRepository(Protocol):
    async def create_agent(
        self,
        *,
        workspace_id: str,
        name: str,
        description: str | None,
        created_by_user_id: str,
        initial_config: AgentConfig,
    ) -> tuple[Agent, AgentVersion]:
        """Creates the agent and its first version (version_number=1) in
        one transaction — an agent without at least one version can
        never be run.
        """
        ...

    async def get_agent(self, *, workspace_id: str, agent_id: str) -> Agent | None: ...

    async def list_agents(self, *, workspace_id: str) -> list[Agent]: ...

    async def search_agents(
        self, *, workspace_id: str, tsquery: str, limit: int
    ) -> list[SearchMatch]: ...

    async def get_version(self, *, agent_id: str, version_id: str) -> AgentVersion | None: ...

    async def get_latest_version(self, *, agent_id: str) -> AgentVersion | None: ...

    async def create_version(
        self, *, agent_id: str, config: AgentConfig, created_by_user_id: str
    ) -> AgentVersion: ...

    async def publish_version(self, *, agent_id: str, version_id: str) -> Agent: ...

    async def soft_delete(self, *, workspace_id: str, agent_id: str) -> None: ...
