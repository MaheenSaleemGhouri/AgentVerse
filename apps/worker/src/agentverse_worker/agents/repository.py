"""Narrow read/write access to `agent_versions`/`agent_runs`/
`agent_run_steps` for the job executor — not a general-purpose
repository, just the handful of operations `agent_run_job.py` needs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_worker.agents.tables import (
    agent_run_steps_table,
    agent_runs_table,
    agent_versions_table,
    agents_table,
)


@dataclass(frozen=True, slots=True)
class RunRecord:
    id: str
    workspace_id: str
    agent_id: str
    agent_version_id: str
    status: str
    input: dict[str, Any]
    cost_micro_usd: int | None = None


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
    async def create_run(
        self,
        *,
        workspace_id: str,
        agent_id: str,
        agent_version_id: str,
        input: dict[str, Any],
    ) -> RunRecord:
        """Used only by the workflow engine (`workflow_node_job.py`) to
        create a sub-run for an `agent_step` node — the API-side
        submission use case (`run_agent.py`) is a separate deployable
        service and cannot be imported here (CLAUDE.md §5); this mirrors
        `SqlAgentRunRepository.create_run`'s row shape exactly, agreeing
        only on the schema, not the code.
        """
        ...

    async def get_final_output(self, run_id: str) -> str | None:
        """The text of the last `llm_call` step — `agent_runs` carries no
        `output` column of its own (unlike `team_sessions`), so a
        workflow node needs this to populate its own output for
        downstream input templating / conditional branching.
        """
        ...

    async def get_published_version_id(self, agent_id: str) -> str | None:
        """Used only by the workflow engine: an `agent_step` node targets
        an `agent_id`, resolved to its currently published version at
        execution time — the same rule `run_agent.py`'s `_resolve_
        runnable_version` applies on the API side.
        """
        ...

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
            cost_micro_usd=row["cost_micro_usd"],
        )

    async def get_version(self, version_id: str) -> VersionRecord | None:
        result = await self._session.execute(
            select(agent_versions_table).where(agent_versions_table.c.id == version_id)
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        return VersionRecord(id=row["id"], agent_id=row["agent_id"], config=row["config"])

    async def create_run(
        self,
        *,
        workspace_id: str,
        agent_id: str,
        agent_version_id: str,
        input: dict[str, Any],
    ) -> RunRecord:
        run_id = str(uuid.uuid4())
        await self._session.execute(
            agent_runs_table.insert().values(
                id=run_id,
                workspace_id=workspace_id,
                agent_id=agent_id,
                agent_version_id=agent_version_id,
                status="queued",
                input=input,
                idempotency_key=None,
                created_at=datetime.now(UTC),
            )
        )
        await self._session.commit()
        return RunRecord(
            id=run_id,
            workspace_id=workspace_id,
            agent_id=agent_id,
            agent_version_id=agent_version_id,
            status="queued",
            input=input,
        )

    async def get_final_output(self, run_id: str) -> str | None:
        result = await self._session.execute(
            select(agent_run_steps_table.c.payload)
            .where(
                agent_run_steps_table.c.run_id == run_id,
                agent_run_steps_table.c.step_type == "llm_call",
            )
            .order_by(agent_run_steps_table.c.sequence.desc())
            .limit(1)
        )
        row = result.one_or_none()
        if row is None:
            return None
        payload: dict[str, Any] = row[0]
        text = payload.get("text")
        return str(text) if text is not None else None

    async def get_published_version_id(self, agent_id: str) -> str | None:
        result = await self._session.execute(
            select(agents_table.c.published_version_id).where(agents_table.c.id == agent_id)
        )
        row = result.one_or_none()
        return str(row[0]) if row is not None and row[0] is not None else None

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
