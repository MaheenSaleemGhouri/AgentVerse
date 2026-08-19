"""Postgres implementation of `WorkflowRunRepository`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.orchestration_service.domain.workflow_entities import (
    WorkflowNodeRun,
    WorkflowNodeRunStatus,
    WorkflowRun,
    WorkflowRunStatus,
)
from agentverse_api.orchestration_service.infrastructure.models import (
    WorkflowNodeRunModel,
    WorkflowRunModel,
)


def _to_run(row: WorkflowRunModel) -> WorkflowRun:
    return WorkflowRun(
        id=row.id,
        workspace_id=row.workspace_id,
        workflow_id=row.workflow_id,
        workflow_version_id=row.workflow_version_id,
        status=WorkflowRunStatus(row.status),
        input=row.input,
        idempotency_key=row.idempotency_key,
        cost_micro_usd=row.cost_micro_usd,
        error_message=row.error_message,
        started_at=row.started_at,
        completed_at=row.completed_at,
        created_at=row.created_at,
    )


def _to_node_run(row: WorkflowNodeRunModel) -> WorkflowNodeRun:
    return WorkflowNodeRun(
        id=row.id,
        workflow_run_id=row.workflow_run_id,
        node_id=row.node_id,
        agent_run_id=row.agent_run_id,
        team_session_id=row.team_session_id,
        status=WorkflowNodeRunStatus(row.status),
        output=row.output,
        approval_decision=row.approval_decision,
        approved_by_user_id=row.approved_by_user_id,
        approved_at=row.approved_at,
        sequence=row.sequence,
        started_at=row.started_at,
        completed_at=row.completed_at,
        created_at=row.created_at,
    )


class SqlWorkflowRunRepository:
    """Implements `domain.ports.workflow_run_repository.WorkflowRunRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_run(
        self,
        *,
        workspace_id: str,
        workflow_id: str,
        workflow_version_id: str,
        input: dict[str, Any],
        idempotency_key: str | None,
    ) -> WorkflowRun:
        row = WorkflowRunModel(
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            workflow_version_id=workflow_version_id,
            status=WorkflowRunStatus.QUEUED,
            input=input,
            idempotency_key=idempotency_key,
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return _to_run(row)

    async def get_run_by_idempotency_key(
        self, *, workflow_id: str, idempotency_key: str
    ) -> WorkflowRun | None:
        result = await self._session.execute(
            select(WorkflowRunModel).where(
                WorkflowRunModel.workflow_id == workflow_id,
                WorkflowRunModel.idempotency_key == idempotency_key,
            )
        )
        row = result.scalar_one_or_none()
        return _to_run(row) if row is not None else None

    async def get_run(self, *, workspace_id: str, run_id: str) -> WorkflowRun | None:
        result = await self._session.execute(
            select(WorkflowRunModel).where(
                WorkflowRunModel.id == run_id, WorkflowRunModel.workspace_id == workspace_id
            )
        )
        row = result.scalar_one_or_none()
        return _to_run(row) if row is not None else None

    async def update_run_status(
        self, *, run_id: str, status: str, error_message: str | None = None
    ) -> None:
        result = await self._session.execute(
            select(WorkflowRunModel).where(WorkflowRunModel.id == run_id)
        )
        row = result.scalar_one()
        row.status = status
        now = datetime.now(UTC)
        if status == "running" and row.started_at is None:
            row.started_at = now
        if status in ("success", "error", "cancelled"):
            row.completed_at = now
        if error_message is not None:
            row.error_message = error_message
        await self._session.flush()

    async def list_node_runs(self, *, workflow_run_id: str) -> list[WorkflowNodeRun]:
        result = await self._session.execute(
            select(WorkflowNodeRunModel)
            .where(WorkflowNodeRunModel.workflow_run_id == workflow_run_id)
            .order_by(WorkflowNodeRunModel.sequence)
        )
        return [_to_node_run(r) for r in result.scalars()]

    async def get_node_run(
        self, *, workflow_run_id: str, node_id: str
    ) -> WorkflowNodeRun | None:
        result = await self._session.execute(
            select(WorkflowNodeRunModel).where(
                WorkflowNodeRunModel.workflow_run_id == workflow_run_id,
                WorkflowNodeRunModel.node_id == node_id,
            )
        )
        row = result.scalar_one_or_none()
        return _to_node_run(row) if row is not None else None

    async def resolve_approval(
        self, *, node_run_id: str, decision: str, approved_by_user_id: str
    ) -> WorkflowNodeRun:
        result = await self._session.execute(
            select(WorkflowNodeRunModel).where(WorkflowNodeRunModel.id == node_run_id)
        )
        row = result.scalar_one()
        row.status = "success" if decision == "approved" else "error"
        row.approval_decision = decision
        row.approved_by_user_id = approved_by_user_id
        row.approved_at = datetime.now(UTC)
        row.completed_at = datetime.now(UTC)
        await self._session.flush()
        return _to_node_run(row)
