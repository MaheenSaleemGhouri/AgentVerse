"""Narrow read/write access to the workflow tables for the DAG
executor — not a general-purpose repository, just what a running
workflow node needs (mirrors `agents/repository.py`/`teams/repository.py`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_worker.workflows.tables import (
    workflow_edges_table,
    workflow_node_runs_table,
    workflow_nodes_table,
    workflow_runs_table,
)

_TERMINAL_NODE_RUN_STATUSES = frozenset({"success", "error", "cancelled", "skipped"})


@dataclass(frozen=True, slots=True)
class WorkflowRunRecord:
    id: str
    workspace_id: str
    workflow_id: str
    workflow_version_id: str
    status: str
    input: dict[str, Any]


@dataclass(frozen=True, slots=True)
class WorkflowNodeRecord:
    id: str
    type: str
    config: dict[str, Any]
    agent_id: str | None
    team_id: str | None


@dataclass(frozen=True, slots=True)
class WorkflowEdgeRecord:
    id: str
    from_node_id: str
    to_node_id: str
    condition: dict[str, Any] | None
    branch_order: int | None


@dataclass(frozen=True, slots=True)
class WorkflowNodeRunRecord:
    id: str
    workflow_run_id: str
    node_id: str
    status: str
    output: dict[str, Any] | None
    agent_run_id: str | None
    team_session_id: str | None
    sequence: int

    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_NODE_RUN_STATUSES


class WorkflowRepositoryProtocol(Protocol):
    """The engine depends on this rather than the concrete class, so
    node-dispatch/advance logic is unit-testable against an in-memory
    fake without a live Postgres (CLAUDE.md §11).
    """

    async def get_run(self, run_id: str) -> WorkflowRunRecord | None: ...
    async def get_nodes_and_edges(
        self, workflow_version_id: str
    ) -> tuple[list[WorkflowNodeRecord], list[WorkflowEdgeRecord]]: ...
    async def update_run_status(
        self,
        *,
        run_id: str,
        status: str,
        error_message: str | None = None,
    ) -> None: ...
    async def add_run_cost(self, *, run_id: str, delta_micro_usd: int) -> None: ...
    async def get_node_run(
        self, *, workflow_run_id: str, node_id: str
    ) -> WorkflowNodeRunRecord | None: ...
    async def list_node_runs(self, *, workflow_run_id: str) -> list[WorkflowNodeRunRecord]: ...
    async def create_node_run(
        self, *, workflow_run_id: str, node_id: str, status: str, sequence: int
    ) -> WorkflowNodeRunRecord: ...
    async def update_node_run(
        self,
        *,
        node_run_id: str,
        status: str,
        output: dict[str, Any] | None = None,
        agent_run_id: str | None = None,
        team_session_id: str | None = None,
    ) -> None: ...
    async def resolve_approval(
        self, *, node_run_id: str, decision: str, approved_by_user_id: str
    ) -> None: ...


class WorkerWorkflowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_run(self, run_id: str) -> WorkflowRunRecord | None:
        result = await self._session.execute(
            select(workflow_runs_table).where(workflow_runs_table.c.id == run_id)
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        return WorkflowRunRecord(
            id=row["id"],
            workspace_id=row["workspace_id"],
            workflow_id=row["workflow_id"],
            workflow_version_id=row["workflow_version_id"],
            status=row["status"],
            input=row["input"],
        )

    async def get_nodes_and_edges(
        self, workflow_version_id: str
    ) -> tuple[list[WorkflowNodeRecord], list[WorkflowEdgeRecord]]:
        node_rows = await self._session.execute(
            select(workflow_nodes_table).where(
                workflow_nodes_table.c.workflow_version_id == workflow_version_id
            )
        )
        nodes = [
            WorkflowNodeRecord(
                id=r["id"], type=r["type"], config=r["config"], agent_id=r["agent_id"],
                team_id=r["team_id"],
            )
            for r in node_rows.mappings()
        ]
        edge_rows = await self._session.execute(
            select(workflow_edges_table).where(
                workflow_edges_table.c.workflow_version_id == workflow_version_id
            )
        )
        edges = [
            WorkflowEdgeRecord(
                id=r["id"], from_node_id=r["from_node_id"], to_node_id=r["to_node_id"],
                condition=r["condition"], branch_order=r["branch_order"],
            )
            for r in edge_rows.mappings()
        ]
        return nodes, edges

    async def update_run_status(
        self, *, run_id: str, status: str, error_message: str | None = None
    ) -> None:
        values: dict[str, Any] = {"status": status}
        now = datetime.now(UTC)
        if status == "running":
            values["started_at"] = now
        if status in ("success", "error", "cancelled"):
            values["completed_at"] = now
        if error_message is not None:
            values["error_message"] = error_message
        await self._session.execute(
            update(workflow_runs_table).where(workflow_runs_table.c.id == run_id).values(**values)
        )
        await self._session.commit()

    async def add_run_cost(self, *, run_id: str, delta_micro_usd: int) -> None:
        # A single atomic UPDATE, not read-then-write — sibling branches
        # of a parallel fan-out may finish and record cost concurrently.
        await self._session.execute(
            text(
                "UPDATE workflow_runs SET cost_micro_usd = COALESCE(cost_micro_usd, 0) + :delta "
                "WHERE id = :run_id"
            ),
            {"delta": delta_micro_usd, "run_id": run_id},
        )
        await self._session.commit()

    async def get_node_run(
        self, *, workflow_run_id: str, node_id: str
    ) -> WorkflowNodeRunRecord | None:
        result = await self._session.execute(
            select(workflow_node_runs_table).where(
                workflow_node_runs_table.c.workflow_run_id == workflow_run_id,
                workflow_node_runs_table.c.node_id == node_id,
            )
        )
        row = result.mappings().one_or_none()
        return _to_node_run(row) if row is not None else None

    async def list_node_runs(self, *, workflow_run_id: str) -> list[WorkflowNodeRunRecord]:
        result = await self._session.execute(
            select(workflow_node_runs_table).where(
                workflow_node_runs_table.c.workflow_run_id == workflow_run_id
            )
        )
        return [_to_node_run(r) for r in result.mappings()]

    async def create_node_run(
        self, *, workflow_run_id: str, node_id: str, status: str, sequence: int
    ) -> WorkflowNodeRunRecord:
        node_run_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        await self._session.execute(
            workflow_node_runs_table.insert().values(
                id=node_run_id,
                created_at=now,
                workflow_run_id=workflow_run_id,
                node_id=node_id,
                status=status,
                sequence=sequence,
                started_at=now if status == "running" else None,
            )
        )
        await self._session.commit()
        return WorkflowNodeRunRecord(
            id=node_run_id, workflow_run_id=workflow_run_id, node_id=node_id, status=status,
            output=None, agent_run_id=None, team_session_id=None, sequence=sequence,
        )

    async def update_node_run(
        self,
        *,
        node_run_id: str,
        status: str,
        output: dict[str, Any] | None = None,
        agent_run_id: str | None = None,
        team_session_id: str | None = None,
    ) -> None:
        values: dict[str, Any] = {"status": status}
        now = datetime.now(UTC)
        if status in _TERMINAL_NODE_RUN_STATUSES:
            values["completed_at"] = now
        if output is not None:
            values["output"] = output
        if agent_run_id is not None:
            values["agent_run_id"] = agent_run_id
        if team_session_id is not None:
            values["team_session_id"] = team_session_id
        await self._session.execute(
            update(workflow_node_runs_table)
            .where(workflow_node_runs_table.c.id == node_run_id)
            .values(**values)
        )
        await self._session.commit()

    async def resolve_approval(
        self, *, node_run_id: str, decision: str, approved_by_user_id: str
    ) -> None:
        status = "success" if decision == "approved" else "error"
        await self._session.execute(
            update(workflow_node_runs_table)
            .where(workflow_node_runs_table.c.id == node_run_id)
            .values(
                status=status,
                approval_decision=decision,
                approved_by_user_id=approved_by_user_id,
                approved_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
        )
        await self._session.commit()


def _to_node_run(row: Any) -> WorkflowNodeRunRecord:
    return WorkflowNodeRunRecord(
        id=row["id"],
        workflow_run_id=row["workflow_run_id"],
        node_id=row["node_id"],
        status=row["status"],
        output=row["output"],
        agent_run_id=row["agent_run_id"],
        team_session_id=row["team_session_id"],
        sequence=row["sequence"],
    )
