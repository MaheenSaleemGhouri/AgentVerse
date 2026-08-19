"""Postgres implementation of `WorkflowRepository`."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.orchestration_service.domain.workflow_entities import (
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeType,
    WorkflowStatus,
    WorkflowVersion,
)
from agentverse_api.orchestration_service.infrastructure.models import (
    WorkflowEdgeModel,
    WorkflowModel,
    WorkflowNodeModel,
    WorkflowVersionModel,
)


def _to_workflow(row: WorkflowModel) -> Workflow:
    return Workflow(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        description=row.description,
        status=WorkflowStatus(row.status),
        published_version_id=row.published_version_id,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_node(row: WorkflowNodeModel) -> WorkflowNode:
    return WorkflowNode(
        id=row.id,
        type=WorkflowNodeType(row.type),
        position_x=row.position_x,
        position_y=row.position_y,
        config=row.config,
        agent_id=row.agent_id,
        team_id=row.team_id,
    )


def _to_edge(row: WorkflowEdgeModel) -> WorkflowEdge:
    return WorkflowEdge(
        id=row.id,
        from_node_id=row.from_node_id,
        to_node_id=row.to_node_id,
        condition=row.condition,
        branch_order=row.branch_order,
    )


class SqlWorkflowRepository:
    """Implements `domain.ports.workflow_repository.WorkflowRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_workflow(
        self,
        *,
        workspace_id: str,
        name: str,
        description: str | None,
        created_by_user_id: str,
    ) -> tuple[Workflow, WorkflowVersion]:
        now = datetime.now(UTC)
        workflow_row = WorkflowModel(
            workspace_id=workspace_id,
            name=name,
            description=description,
            status=WorkflowStatus.DRAFT,
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
        )
        self._session.add(workflow_row)
        await self._session.flush()

        version_row = WorkflowVersionModel(
            workflow_id=workflow_row.id,
            version_number=1,
            created_by_user_id=created_by_user_id,
            created_at=now,
        )
        self._session.add(version_row)
        await self._session.flush()

        return _to_workflow(workflow_row), WorkflowVersion(
            id=version_row.id,
            workflow_id=workflow_row.id,
            version_number=1,
            nodes=[],
            edges=[],
            created_by_user_id=created_by_user_id,
            created_at=now,
        )

    async def get_workflow(self, *, workspace_id: str, workflow_id: str) -> Workflow | None:
        result = await self._session.execute(
            select(WorkflowModel).where(
                WorkflowModel.id == workflow_id, WorkflowModel.workspace_id == workspace_id
            )
        )
        row = result.scalar_one_or_none()
        return _to_workflow(row) if row is not None else None

    async def list_workflows(self, *, workspace_id: str) -> list[Workflow]:
        result = await self._session.execute(
            select(WorkflowModel)
            .where(WorkflowModel.workspace_id == workspace_id)
            .order_by(WorkflowModel.created_at.desc())
        )
        return [_to_workflow(row) for row in result.scalars()]

    async def _load_version(self, row: WorkflowVersionModel) -> WorkflowVersion:
        nodes_result = await self._session.execute(
            select(WorkflowNodeModel).where(WorkflowNodeModel.workflow_version_id == row.id)
        )
        nodes = [_to_node(n) for n in nodes_result.scalars()]

        edges_result = await self._session.execute(
            select(WorkflowEdgeModel).where(WorkflowEdgeModel.workflow_version_id == row.id)
        )
        edges = [_to_edge(e) for e in edges_result.scalars()]

        return WorkflowVersion(
            id=row.id,
            workflow_id=row.workflow_id,
            version_number=row.version_number,
            nodes=nodes,
            edges=edges,
            created_by_user_id=row.created_by_user_id,
            created_at=row.created_at,
        )

    async def get_version(self, *, workflow_id: str, version_id: str) -> WorkflowVersion | None:
        result = await self._session.execute(
            select(WorkflowVersionModel).where(
                WorkflowVersionModel.id == version_id,
                WorkflowVersionModel.workflow_id == workflow_id,
            )
        )
        row = result.scalar_one_or_none()
        return await self._load_version(row) if row is not None else None

    async def get_latest_version(self, *, workflow_id: str) -> WorkflowVersion | None:
        result = await self._session.execute(
            select(WorkflowVersionModel)
            .where(WorkflowVersionModel.workflow_id == workflow_id)
            .order_by(WorkflowVersionModel.version_number.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return await self._load_version(row) if row is not None else None

    async def create_version(
        self,
        *,
        workflow_id: str,
        nodes: list[WorkflowNode],
        edges: list[WorkflowEdge],
        created_by_user_id: str,
    ) -> WorkflowVersion:
        latest = await self.get_latest_version(workflow_id=workflow_id)
        next_number = (latest.version_number + 1) if latest is not None else 1
        now = datetime.now(UTC)

        version_row = WorkflowVersionModel(
            workflow_id=workflow_id,
            version_number=next_number,
            created_by_user_id=created_by_user_id,
            created_at=now,
        )
        self._session.add(version_row)
        await self._session.flush()

        # Nodes before edges: edges FK into workflow_nodes.
        for node in nodes:
            self._session.add(
                WorkflowNodeModel(
                    id=node.id,
                    workflow_version_id=version_row.id,
                    type=node.type.value,
                    position_x=node.position_x,
                    position_y=node.position_y,
                    config=node.config,
                    agent_id=node.agent_id,
                    team_id=node.team_id,
                )
            )
        await self._session.flush()

        for edge in edges:
            self._session.add(
                WorkflowEdgeModel(
                    id=edge.id,
                    workflow_version_id=version_row.id,
                    from_node_id=edge.from_node_id,
                    to_node_id=edge.to_node_id,
                    condition=edge.condition,
                    branch_order=edge.branch_order,
                )
            )
        await self._session.flush()

        return WorkflowVersion(
            id=version_row.id,
            workflow_id=workflow_id,
            version_number=next_number,
            nodes=nodes,
            edges=edges,
            created_by_user_id=created_by_user_id,
            created_at=now,
        )

    async def publish_version(self, *, workflow_id: str, version_id: str) -> Workflow:
        result = await self._session.execute(
            select(WorkflowModel).where(WorkflowModel.id == workflow_id)
        )
        workflow_row = result.scalar_one()
        workflow_row.published_version_id = version_id
        workflow_row.status = WorkflowStatus.ACTIVE
        workflow_row.updated_at = datetime.now(UTC)
        await self._session.flush()
        return _to_workflow(workflow_row)
