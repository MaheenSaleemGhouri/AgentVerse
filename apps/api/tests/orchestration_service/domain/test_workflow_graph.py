"""Unit tests for `validate_workflow_graph` — pure, zero I/O."""

from __future__ import annotations

import pytest

from agentverse_api.orchestration_service.domain.workflow_entities import (
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeType,
)
from agentverse_api.orchestration_service.domain.workflow_exceptions import (
    InvalidWorkflowGraphError,
)
from agentverse_api.orchestration_service.domain.workflow_graph import validate_workflow_graph


def _node(
    node_id: str, node_type: WorkflowNodeType = WorkflowNodeType.PARALLEL_FANOUT
) -> WorkflowNode:
    return WorkflowNode(id=node_id, type=node_type, position_x=0, position_y=0, config={})


def test_empty_graph_is_valid() -> None:
    validate_workflow_graph([], [])


def test_single_node_no_edges_is_valid() -> None:
    validate_workflow_graph([_node("a")], [])


def test_linear_chain_is_valid() -> None:
    nodes = [_node("a"), _node("b"), _node("c")]
    edges = [
        WorkflowEdge(id="e1", from_node_id="a", to_node_id="b"),
        WorkflowEdge(id="e2", from_node_id="b", to_node_id="c"),
    ]
    validate_workflow_graph(nodes, edges)


def test_duplicate_node_id_is_rejected() -> None:
    with pytest.raises(InvalidWorkflowGraphError, match="Duplicate"):
        validate_workflow_graph([_node("a"), _node("a")], [])


def test_edge_referencing_unknown_node_is_rejected() -> None:
    with pytest.raises(InvalidWorkflowGraphError, match="unknown"):
        validate_workflow_graph(
            [_node("a")], [WorkflowEdge(id="e1", from_node_id="a", to_node_id="ghost")]
        )


def test_self_loop_edge_is_rejected() -> None:
    with pytest.raises(InvalidWorkflowGraphError, match="self-loop"):
        validate_workflow_graph(
            [_node("a")], [WorkflowEdge(id="e1", from_node_id="a", to_node_id="a")]
        )


def test_two_node_cycle_is_rejected() -> None:
    edges = [
        WorkflowEdge(id="e1", from_node_id="a", to_node_id="b"),
        WorkflowEdge(id="e2", from_node_id="b", to_node_id="a"),
    ]
    with pytest.raises(InvalidWorkflowGraphError, match="cycle"):
        validate_workflow_graph([_node("a"), _node("b")], edges)


def test_three_node_cycle_is_rejected() -> None:
    edges = [
        WorkflowEdge(id="e1", from_node_id="a", to_node_id="b"),
        WorkflowEdge(id="e2", from_node_id="b", to_node_id="c"),
        WorkflowEdge(id="e3", from_node_id="c", to_node_id="a"),
    ]
    with pytest.raises(InvalidWorkflowGraphError, match="cycle"):
        validate_workflow_graph([_node("a"), _node("b"), _node("c")], edges)


def test_agent_step_without_agent_id_is_rejected() -> None:
    node = WorkflowNode(
        id="a", type=WorkflowNodeType.AGENT_STEP, position_x=0, position_y=0, config={}
    )
    with pytest.raises(InvalidWorkflowGraphError, match="agent_step"):
        validate_workflow_graph([node], [])


def test_agent_step_with_team_id_instead_is_rejected() -> None:
    node = WorkflowNode(
        id="a",
        type=WorkflowNodeType.AGENT_STEP,
        position_x=0,
        position_y=0,
        config={},
        team_id="team-1",
    )
    with pytest.raises(InvalidWorkflowGraphError, match="agent_step"):
        validate_workflow_graph([node], [])


def test_team_step_without_team_id_is_rejected() -> None:
    node = WorkflowNode(
        id="a", type=WorkflowNodeType.TEAM_STEP, position_x=0, position_y=0, config={}
    )
    with pytest.raises(InvalidWorkflowGraphError, match="team_step"):
        validate_workflow_graph([node], [])


def test_non_executable_node_carrying_agent_id_is_rejected() -> None:
    node = WorkflowNode(
        id="a",
        type=WorkflowNodeType.CONDITIONAL_BRANCH,
        position_x=0,
        position_y=0,
        config={},
        agent_id="agent-1",
    )
    with pytest.raises(InvalidWorkflowGraphError, match="must not carry"):
        validate_workflow_graph([node], [])


def test_valid_agent_step_and_human_approval_chain() -> None:
    nodes = [
        WorkflowNode(
            id="a",
            type=WorkflowNodeType.AGENT_STEP,
            position_x=0,
            position_y=0,
            config={},
            agent_id="agent-1",
        ),
        WorkflowNode(
            id="b", type=WorkflowNodeType.HUMAN_APPROVAL, position_x=0, position_y=0, config={}
        ),
    ]
    edges = [WorkflowEdge(id="e1", from_node_id="a", to_node_id="b")]
    validate_workflow_graph(nodes, edges)
