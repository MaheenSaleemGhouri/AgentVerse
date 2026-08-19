"""Pure structural validation for a workflow node/edge graph — zero I/O,
unit-tested directly (CLAUDE.md §11: routing/permission-shaped decisions
are pure functions). Called before a version is persisted, so an author
learns about a broken graph at save time, not from a run that can never
complete.
"""

from __future__ import annotations

from agentverse_api.orchestration_service.domain.workflow_entities import (
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeType,
)
from agentverse_api.orchestration_service.domain.workflow_exceptions import (
    InvalidWorkflowGraphError,
)


def validate_workflow_graph(nodes: list[WorkflowNode], edges: list[WorkflowEdge]) -> None:
    if not nodes:
        return  # an empty draft (a brand-new workflow) is valid — nothing to run yet

    node_ids = [n.id for n in nodes]
    if len(node_ids) != len(set(node_ids)):
        raise InvalidWorkflowGraphError("Duplicate node id in graph")
    node_id_set = set(node_ids)

    for node in nodes:
        _validate_node_target(node)

    for edge in edges:
        if edge.from_node_id not in node_id_set:
            raise InvalidWorkflowGraphError(
                f"Edge {edge.id!r} references unknown from_node_id {edge.from_node_id!r}"
            )
        if edge.to_node_id not in node_id_set:
            raise InvalidWorkflowGraphError(
                f"Edge {edge.id!r} references unknown to_node_id {edge.to_node_id!r}"
            )
        if edge.from_node_id == edge.to_node_id:
            raise InvalidWorkflowGraphError(f"Edge {edge.id!r} is a self-loop")

    _assert_acyclic(node_ids, edges)

    targets = {e.to_node_id for e in edges}
    if not any(n.id not in targets for n in nodes):
        raise InvalidWorkflowGraphError(
            "Graph has no start node — every node has an incoming edge"
        )


def _validate_node_target(node: WorkflowNode) -> None:
    if node.type is WorkflowNodeType.AGENT_STEP:
        if node.agent_id is None or node.team_id is not None:
            raise InvalidWorkflowGraphError(
                f"Node {node.id!r} is agent_step but agent_id is unset (or team_id is set)"
            )
    elif node.type is WorkflowNodeType.TEAM_STEP:
        if node.team_id is None or node.agent_id is not None:
            raise InvalidWorkflowGraphError(
                f"Node {node.id!r} is team_step but team_id is unset (or agent_id is set)"
            )
    elif node.agent_id is not None or node.team_id is not None:
        raise InvalidWorkflowGraphError(
            f"Node {node.id!r} is {node.type.value!r} and must not carry agent_id/team_id"
        )


def _assert_acyclic(node_ids: list[str], edges: list[WorkflowEdge]) -> None:
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        adjacency[edge.from_node_id].append(edge.to_node_id)

    unvisited, visiting, visited = 0, 1, 2
    state: dict[str, int] = dict.fromkeys(node_ids, unvisited)

    def dfs(node_id: str) -> None:
        state[node_id] = visiting
        for neighbor in adjacency[node_id]:
            if state[neighbor] == visiting:
                raise InvalidWorkflowGraphError("Graph contains a cycle")
            if state[neighbor] == unvisited:
                dfs(neighbor)
        state[node_id] = visited

    for node_id in node_ids:
        if state[node_id] == unvisited:
            dfs(node_id)
