"""Create-workflow use case — thin orchestration over the repository
(CLAUDE.md §7: a route never calls a repository directly), mirroring
`create_agent.py`.
"""

from __future__ import annotations

from agentverse_api.orchestration_service.domain.ports.workflow_repository import (
    WorkflowRepository,
)
from agentverse_api.orchestration_service.domain.workflow_entities import Workflow, WorkflowVersion


async def create_workflow(
    *,
    workspace_id: str,
    name: str,
    description: str | None,
    created_by_user_id: str,
    workflow_repo: WorkflowRepository,
) -> tuple[Workflow, WorkflowVersion]:
    return await workflow_repo.create_workflow(
        workspace_id=workspace_id,
        name=name,
        description=description,
        created_by_user_id=created_by_user_id,
    )
