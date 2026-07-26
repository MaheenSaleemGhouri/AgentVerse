"""In-memory fakes implementing the agent/run repository ports — used
by unit tests so application-layer logic is tested without I/O
(CLAUDE.md §11). Integration tests use the real `Sql*Repository`
classes against Postgres instead.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentverse_api.orchestration_service.domain.agent_entities import (
    Agent,
    AgentConfig,
    AgentStatus,
    AgentVersion,
)
from agentverse_api.orchestration_service.domain.run_entities import (
    AgentRun,
    AgentRunStep,
    RunStatus,
)


@dataclass
class FakeAgentRepository:
    agents: dict[str, Agent] = field(default_factory=dict)
    versions: dict[str, list[AgentVersion]] = field(default_factory=dict)

    async def create_agent(
        self,
        *,
        workspace_id: str,
        name: str,
        description: str | None,
        created_by_user_id: str,
        initial_config: AgentConfig,
    ) -> tuple[Agent, AgentVersion]:
        now = datetime.now(UTC)
        agent = Agent(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            name=name,
            description=description,
            status=AgentStatus.DRAFT,
            published_version_id=None,
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
        )
        version = AgentVersion(
            id=str(uuid.uuid4()),
            agent_id=agent.id,
            version_number=1,
            config=initial_config,
            created_by_user_id=created_by_user_id,
            created_at=now,
        )
        self.agents[agent.id] = agent
        self.versions[agent.id] = [version]
        return agent, version

    async def get_agent(self, *, workspace_id: str, agent_id: str) -> Agent | None:
        agent = self.agents.get(agent_id)
        if agent is None or agent.workspace_id != workspace_id:
            return None
        return agent

    async def list_agents(self, *, workspace_id: str) -> list[Agent]:
        return [a for a in self.agents.values() if a.workspace_id == workspace_id]

    async def get_version(self, *, agent_id: str, version_id: str) -> AgentVersion | None:
        return next(
            (v for v in self.versions.get(agent_id, []) if v.id == version_id),
            None,
        )

    async def get_latest_version(self, *, agent_id: str) -> AgentVersion | None:
        versions = self.versions.get(agent_id, [])
        return max(versions, key=lambda v: v.version_number) if versions else None

    async def create_version(
        self, *, agent_id: str, config: AgentConfig, created_by_user_id: str
    ) -> AgentVersion:
        latest = await self.get_latest_version(agent_id=agent_id)
        next_number = (latest.version_number + 1) if latest is not None else 1
        version = AgentVersion(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            version_number=next_number,
            config=config,
            created_by_user_id=created_by_user_id,
            created_at=datetime.now(UTC),
        )
        self.versions.setdefault(agent_id, []).append(version)
        return version

    async def publish_version(self, *, agent_id: str, version_id: str) -> Agent:
        agent = self.agents[agent_id]
        updated = Agent(
            id=agent.id,
            workspace_id=agent.workspace_id,
            name=agent.name,
            description=agent.description,
            status=AgentStatus.ACTIVE,
            published_version_id=version_id,
            created_by_user_id=agent.created_by_user_id,
            created_at=agent.created_at,
            updated_at=datetime.now(UTC),
        )
        self.agents[agent_id] = updated
        return updated

    async def soft_delete(self, *, workspace_id: str, agent_id: str) -> None:
        self.agents.pop(agent_id, None)


@dataclass
class FakeAgentRunRepository:
    runs: dict[str, AgentRun] = field(default_factory=dict)
    steps: dict[str, list[AgentRunStep]] = field(default_factory=dict)

    async def create_run(
        self,
        *,
        workspace_id: str,
        agent_id: str,
        agent_version_id: str,
        input: dict[str, Any],
        idempotency_key: str | None,
    ) -> AgentRun:
        run = AgentRun(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            status=RunStatus.QUEUED,
            input=input,
            idempotency_key=idempotency_key,
            cost_micro_usd=None,
            error_message=None,
            started_at=None,
            completed_at=None,
            created_at=datetime.now(UTC),
        )
        self.runs[run.id] = run
        return run

    async def get_run_by_idempotency_key(
        self, *, workspace_id: str, idempotency_key: str
    ) -> AgentRun | None:
        return next(
            (
                r
                for r in self.runs.values()
                if r.workspace_id == workspace_id and r.idempotency_key == idempotency_key
            ),
            None,
        )

    async def get_run(self, *, workspace_id: str, run_id: str) -> AgentRun | None:
        run = self.runs.get(run_id)
        if run is None or run.workspace_id != workspace_id:
            return None
        return run

    async def update_status(
        self,
        *,
        run_id: str,
        status: RunStatus,
        cost_micro_usd: int | None = None,
        error_message: str | None = None,
    ) -> None:
        run = self.runs[run_id]
        self.runs[run_id] = AgentRun(
            id=run.id,
            workspace_id=run.workspace_id,
            agent_id=run.agent_id,
            agent_version_id=run.agent_version_id,
            status=status,
            input=run.input,
            idempotency_key=run.idempotency_key,
            cost_micro_usd=cost_micro_usd if cost_micro_usd is not None else run.cost_micro_usd,
            error_message=error_message if error_message is not None else run.error_message,
            started_at=run.started_at,
            completed_at=run.completed_at,
            created_at=run.created_at,
        )

    async def append_step(self, step: AgentRunStep) -> None:
        self.steps.setdefault(step.run_id, []).append(step)

    async def list_steps(self, *, run_id: str) -> list[AgentRunStep]:
        return sorted(self.steps.get(run_id, []), key=lambda s: s.sequence)
