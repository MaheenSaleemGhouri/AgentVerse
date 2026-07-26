"""Narrow read/write access to `agent_versions`/`agent_runs`/
`agent_run_steps` for the job executor — not a general-purpose
repository, just the handful of operations `agent_run_job.py` needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_worker.agents.tables import (
    agent_run_steps_table,
    agent_runs_table,
    agent_versions_table,
)


@dataclass(frozen=True, slots=True)
class RunRecord:
    id: str
    workspace_id: str
    agent_id: str
    agent_version_id: str
    status: str
    input: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VersionRecord:
    id: str
    agent_id: str
    config: dict[str, Any]


class AgentRepositoryProtocol(Protocol):
    """`agent_run_job.py` depends on this, not the concrete
    `WorkerAgentRepository` — unit tests substitute an in-memory fake
    (CLAUDE.md §11) instead of needing a live Postgres.
    """

    async def get_run(self, run_id: str) -> RunRecord | None: ...
    async def get_version(self, version_id: str) -> VersionRecord | None: ...
    async def update_run_status(
        self,
        *,
        run_id: str,
        status: str,
        cost_micro_usd: int | None = None,
        error_message: str | None = None,
    ) -> None: ...
    async def append_step(
        self,
        *,
        step_id: str,
        run_id: str,
        workspace_id: str,
        step_type: str,
        sequence: int,
        payload: dict[str, Any],
        cost_micro_usd: int | None,
    ) -> None: ...


class WorkerAgentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_run(self, run_id: str) -> RunRecord | None:
        result = await self._session.execute(
            select(agent_runs_table).where(agent_runs_table.c.id == run_id)
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        return RunRecord(
            id=row["id"],
            workspace_id=row["workspace_id"],
            agent_id=row["agent_id"],
            agent_version_id=row["agent_version_id"],
            status=row["status"],
            input=row["input"],
        )

    async def get_version(self, version_id: str) -> VersionRecord | None:
        result = await self._session.execute(
            select(agent_versions_table).where(agent_versions_table.c.id == version_id)
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        return VersionRecord(id=row["id"], agent_id=row["agent_id"], config=row["config"])

    async def update_run_status(
        self,
        *,
        run_id: str,
        status: str,
        cost_micro_usd: int | None = None,
        error_message: str | None = None,
    ) -> None:
        values: dict[str, Any] = {"status": status}
        now = datetime.now(UTC)
        if status == "running":
            values["started_at"] = now
        if status in ("success", "error", "cancelled"):
            values["completed_at"] = now
        if cost_micro_usd is not None:
            values["cost_micro_usd"] = cost_micro_usd
        if error_message is not None:
            values["error_message"] = error_message
        await self._session.execute(
            update(agent_runs_table).where(agent_runs_table.c.id == run_id).values(**values)
        )
        await self._session.commit()

    async def append_step(
        self,
        *,
        step_id: str,
        run_id: str,
        workspace_id: str,
        step_type: str,
        sequence: int,
        payload: dict[str, Any],
        cost_micro_usd: int | None,
    ) -> None:
        await self._session.execute(
            agent_run_steps_table.insert().values(
                id=step_id,
                run_id=run_id,
                workspace_id=workspace_id,
                step_type=step_type,
                sequence=sequence,
                payload=payload,
                cost_micro_usd=cost_micro_usd,
                created_at=datetime.now(UTC),
            )
        )
        await self._session.commit()
