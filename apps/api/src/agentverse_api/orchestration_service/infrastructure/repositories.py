"""Postgres implementations of `domain/ports/*.py`'s repository protocols."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from agentverse_api.orchestration_service.infrastructure.models import (
    AgentModel,
    AgentRunModel,
    AgentRunStepModel,
    AgentVersionModel,
)


def _to_config(raw: dict[str, Any]) -> AgentConfig:
    return AgentConfig(
        model=raw["model"],
        system_instructions=raw["system_instructions"],
        temperature=raw.get("temperature"),
        max_output_tokens=raw.get("max_output_tokens"),
        tools=list(raw.get("tools", [])),
    )


def _config_to_dict(config: AgentConfig) -> dict[str, Any]:
    return {
        "model": config.model,
        "system_instructions": config.system_instructions,
        "temperature": config.temperature,
        "max_output_tokens": config.max_output_tokens,
        "tools": config.tools,
    }


def _to_agent(row: AgentModel) -> Agent:
    return Agent(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        description=row.description,
        status=row.status,
        published_version_id=row.published_version_id,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_version(row: AgentVersionModel) -> AgentVersion:
    return AgentVersion(
        id=row.id,
        agent_id=row.agent_id,
        version_number=row.version_number,
        config=_to_config(row.config),
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


def _to_run(row: AgentRunModel) -> AgentRun:
    return AgentRun(
        id=row.id,
        workspace_id=row.workspace_id,
        agent_id=row.agent_id,
        agent_version_id=row.agent_version_id,
        status=row.status,
        input=row.input,
        idempotency_key=row.idempotency_key,
        cost_micro_usd=row.cost_micro_usd,
        error_message=row.error_message,
        started_at=row.started_at,
        completed_at=row.completed_at,
        created_at=row.created_at,
    )


def _to_step(row: AgentRunStepModel) -> AgentRunStep:
    return AgentRunStep(
        id=row.id,
        run_id=row.run_id,
        workspace_id=row.workspace_id,
        step_type=row.step_type,
        sequence=row.sequence,
        payload=row.payload,
        cost_micro_usd=row.cost_micro_usd,
        created_at=row.created_at,
    )


class SqlAgentRepository:
    """Implements `domain.ports.agent_repository.AgentRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
        agent_row = AgentModel(
            workspace_id=workspace_id,
            name=name,
            description=description,
            status=AgentStatus.DRAFT,
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
        )
        self._session.add(agent_row)
        await self._session.flush()

        version_row = AgentVersionModel(
            agent_id=agent_row.id,
            version_number=1,
            config=_config_to_dict(initial_config),
            created_by_user_id=created_by_user_id,
            created_at=now,
        )
        self._session.add(version_row)
        await self._session.flush()

        return _to_agent(agent_row), _to_version(version_row)

    async def get_agent(self, *, workspace_id: str, agent_id: str) -> Agent | None:
        result = await self._session.execute(
            select(AgentModel).where(
                AgentModel.id == agent_id,
                AgentModel.workspace_id == workspace_id,
                AgentModel.deleted_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        return _to_agent(row) if row is not None else None

    async def list_agents(self, *, workspace_id: str) -> list[Agent]:
        result = await self._session.execute(
            select(AgentModel)
            .where(AgentModel.workspace_id == workspace_id, AgentModel.deleted_at.is_(None))
            .order_by(AgentModel.created_at.desc())
        )
        return [_to_agent(row) for row in result.scalars()]

    async def get_version(self, *, agent_id: str, version_id: str) -> AgentVersion | None:
        result = await self._session.execute(
            select(AgentVersionModel).where(
                AgentVersionModel.id == version_id, AgentVersionModel.agent_id == agent_id
            )
        )
        row = result.scalar_one_or_none()
        return _to_version(row) if row is not None else None

    async def get_latest_version(self, *, agent_id: str) -> AgentVersion | None:
        result = await self._session.execute(
            select(AgentVersionModel)
            .where(AgentVersionModel.agent_id == agent_id)
            .order_by(AgentVersionModel.version_number.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return _to_version(row) if row is not None else None

    async def create_version(
        self, *, agent_id: str, config: AgentConfig, created_by_user_id: str
    ) -> AgentVersion:
        latest = await self.get_latest_version(agent_id=agent_id)
        next_number = (latest.version_number + 1) if latest is not None else 1
        row = AgentVersionModel(
            agent_id=agent_id,
            version_number=next_number,
            config=_config_to_dict(config),
            created_by_user_id=created_by_user_id,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return _to_version(row)

    async def publish_version(self, *, agent_id: str, version_id: str) -> Agent:
        result = await self._session.execute(select(AgentModel).where(AgentModel.id == agent_id))
        agent_row = result.scalar_one()
        agent_row.published_version_id = version_id
        agent_row.status = AgentStatus.ACTIVE
        agent_row.updated_at = datetime.now(UTC)
        await self._session.flush()
        return _to_agent(agent_row)

    async def soft_delete(self, *, workspace_id: str, agent_id: str) -> None:
        result = await self._session.execute(
            select(AgentModel).where(
                AgentModel.id == agent_id, AgentModel.workspace_id == workspace_id
            )
        )
        agent_row = result.scalar_one()
        agent_row.deleted_at = datetime.now(UTC)
        agent_row.status = AgentStatus.ARCHIVED
        await self._session.flush()


class SqlAgentRunRepository:
    """Implements `domain.ports.run_repository.AgentRunRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_run(
        self,
        *,
        workspace_id: str,
        agent_id: str,
        agent_version_id: str,
        input: dict[str, Any],
        idempotency_key: str | None,
    ) -> AgentRun:
        row = AgentRunModel(
            workspace_id=workspace_id,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            status=RunStatus.QUEUED,
            input=input,
            idempotency_key=idempotency_key,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return _to_run(row)

    async def get_run_by_idempotency_key(
        self, *, workspace_id: str, idempotency_key: str
    ) -> AgentRun | None:
        result = await self._session.execute(
            select(AgentRunModel).where(
                AgentRunModel.workspace_id == workspace_id,
                AgentRunModel.idempotency_key == idempotency_key,
            )
        )
        row = result.scalar_one_or_none()
        return _to_run(row) if row is not None else None

    async def get_run(self, *, workspace_id: str, run_id: str) -> AgentRun | None:
        result = await self._session.execute(
            select(AgentRunModel).where(
                AgentRunModel.id == run_id, AgentRunModel.workspace_id == workspace_id
            )
        )
        row = result.scalar_one_or_none()
        return _to_run(row) if row is not None else None

    async def update_status(
        self,
        *,
        run_id: str,
        status: RunStatus,
        cost_micro_usd: int | None = None,
        error_message: str | None = None,
    ) -> None:
        result = await self._session.execute(
            select(AgentRunModel).where(AgentRunModel.id == run_id)
        )
        row = result.scalar_one()
        row.status = status
        now = datetime.now(UTC)
        if status is RunStatus.RUNNING and row.started_at is None:
            row.started_at = now
        if status in (RunStatus.SUCCESS, RunStatus.ERROR, RunStatus.CANCELLED):
            row.completed_at = now
        if cost_micro_usd is not None:
            row.cost_micro_usd = cost_micro_usd
        if error_message is not None:
            row.error_message = error_message
        await self._session.flush()

    async def append_step(self, step: AgentRunStep) -> None:
        row = AgentRunStepModel(
            id=step.id,
            run_id=step.run_id,
            workspace_id=step.workspace_id,
            step_type=step.step_type,
            sequence=step.sequence,
            payload=step.payload,
            cost_micro_usd=step.cost_micro_usd,
            created_at=step.created_at,
        )
        self._session.add(row)
        await self._session.flush()

    async def list_steps(self, *, run_id: str) -> list[AgentRunStep]:
        result = await self._session.execute(
            select(AgentRunStepModel)
            .where(AgentRunStepModel.run_id == run_id)
            .order_by(AgentRunStepModel.sequence)
        )
        return [_to_step(row) for row in result.scalars()]
