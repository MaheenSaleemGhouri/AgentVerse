"""Repository port (Protocol) for `workflows`/`workflow_versions`/
`workflow_nodes`/`workflow_edges`. `infrastructure/workflow_repository.py`
implements this against Postgres; tests implement it against an
in-memory fake (CLAUDE.md §5).
"""

from __future__ import annotations

from typing import Protocol

from agentverse_api.orchestration_service.domain.workflow_entities import (
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowVersion,
)


class WorkflowRepository(Protocol):
    async def create_workflow(
        self,
        *,
        workspace_id: str,
        name: str,
        description: str | None,
        created_by_user_id: str,
    ) -> tuple[Workflow, WorkflowVersion]:
        """Creates the workflow and an empty first version (version_number=1,
        no nodes/edges) in one transaction — mirrors `AgentRepository.
        create_agent`. The canvas opens on this empty version and the
        first real `create_version` call populates it.
        """
        ...

    async def get_workflow(self, *, workspace_id: str, workflow_id: str) -> Workflow | None: ...

    async def list_workflows(self, *, workspace_id: str) -> list[Workflow]: ...

    async def get_version(
        self, *, workflow_id: str, version_id: str
    ) -> WorkflowVersion | None: ...

    async def get_latest_version(self, *, workflow_id: str) -> WorkflowVersion | None: ...

    async def create_version(
        self,
        *,
        workflow_id: str,
        nodes: list[WorkflowNode],
        edges: list[WorkflowEdge],
        created_by_user_id: str,
    ) -> WorkflowVersion:
        """Writes nodes and edges together, atomically — a version with
        edges referencing nodes from a different version could never
        happen otherwise.
        """
        ...

    async def publish_version(self, *, workflow_id: str, version_id: str) -> Workflow:
        """Unlike `AgentRepository.publish_version`, accepts an explicit
        `version_id` rather than always targeting the latest — this is
        what makes rollback-to-an-arbitrary-version possible.
        """
        ...
