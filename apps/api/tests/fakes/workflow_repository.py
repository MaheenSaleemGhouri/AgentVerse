"""In-memory fake implementing `WorkflowRepository` — used by route-level
tests so the router/schema wiring is tested without I/O (CLAUDE.md §11).
Integration tests use the real `SqlWorkflowRepository` against Postgres
instead.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from agentverse_api.orchestration_service.domain.workflow_entities import (
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowStatus,
    WorkflowVersion,
)


@dataclass
class FakeWorkflowRepository:
    workflows: dict[str, Workflow] = field(default_factory=dict)
    versions: dict[str, list[WorkflowVersion]] = field(default_factory=dict)

    async def create_workflow(
        self,
        *,
        workspace_id: str,
        name: str,
        description: str | None,
        created_by_user_id: str,
    ) -> tuple[Workflow, WorkflowVersion]:
        now = datetime.now(UTC)
        workflow = Workflow(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            name=name,
            description=description,
            status=WorkflowStatus.DRAFT,
            published_version_id=None,
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
        )
        version = WorkflowVersion(
            id=str(uuid.uuid4()),
            workflow_id=workflow.id,
            version_number=1,
            nodes=[],
            edges=[],
            created_by_user_id=created_by_user_id,
            created_at=now,
        )
        self.workflows[workflow.id] = workflow
        self.versions[workflow.id] = [version]
        return workflow, version

    async def get_workflow(self, *, workspace_id: str, workflow_id: str) -> Workflow | None:
        workflow = self.workflows.get(workflow_id)
        if workflow is None or workflow.workspace_id != workspace_id:
            return None
        return workflow

    async def list_workflows(self, *, workspace_id: str) -> list[Workflow]:
        return sorted(
            (w for w in self.workflows.values() if w.workspace_id == workspace_id),
            key=lambda w: w.created_at,
            reverse=True,
        )

    async def get_version(self, *, workflow_id: str, version_id: str) -> WorkflowVersion | None:
        return next(
            (v for v in self.versions.get(workflow_id, []) if v.id == version_id),
            None,
        )

    async def get_latest_version(self, *, workflow_id: str) -> WorkflowVersion | None:
        versions = self.versions.get(workflow_id, [])
        if not versions:
            return None
        return max(versions, key=lambda v: v.version_number)

    async def create_version(
        self,
        *,
        workflow_id: str,
        nodes: list[WorkflowNode],
        edges: list[WorkflowEdge],
        created_by_user_id: str,
    ) -> WorkflowVersion:
        existing = self.versions.setdefault(workflow_id, [])
        next_number = (max((v.version_number for v in existing), default=0)) + 1
        version = WorkflowVersion(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            version_number=next_number,
            nodes=nodes,
            edges=edges,
            created_by_user_id=created_by_user_id,
            created_at=datetime.now(UTC),
        )
        existing.append(version)
        return version

    async def publish_version(self, *, workflow_id: str, version_id: str) -> Workflow:
        workflow = self.workflows[workflow_id]
        published = Workflow(
            id=workflow.id,
            workspace_id=workflow.workspace_id,
            name=workflow.name,
            description=workflow.description,
            status=WorkflowStatus.ACTIVE,
            published_version_id=version_id,
            created_by_user_id=workflow.created_by_user_id,
            created_at=workflow.created_at,
            updated_at=datetime.now(UTC),
        )
        self.workflows[workflow_id] = published
        return published
