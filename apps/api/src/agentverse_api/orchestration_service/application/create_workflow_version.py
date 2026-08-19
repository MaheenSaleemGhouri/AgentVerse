"""Create-workflow-version use case: validates the submitted graph
before persisting it (`workflow_graph.validate_workflow_graph`), unlike
`AgentRepository.create_version`, which has no equivalent structure to
validate — this is genuine logic, not a passthrough, so it lives here
rather than being called directly from the router.
"""

from __future__ import annotations

from agentverse_api.orchestration_service.domain.ports.workflow_repository import (
    WorkflowRepository,
)
from agentverse_api.orchestration_service.domain.workflow_entities import (
    WorkflowEdge,
    WorkflowNode,
    WorkflowVersion,
)
from agentverse_api.orchestration_service.domain.workflow_graph import validate_workflow_graph


async def create_workflow_version(
    *,
    workflow_id: str,
    nodes: list[WorkflowNode],
    edges: list[WorkflowEdge],
    created_by_user_id: str,
    workflow_repo: WorkflowRepository,
) -> WorkflowVersion:
    validate_workflow_graph(nodes, edges)
    return await workflow_repo.create_version(
        workflow_id=workflow_id,
        nodes=nodes,
        edges=edges,
        created_by_user_id=created_by_user_id,
    )
