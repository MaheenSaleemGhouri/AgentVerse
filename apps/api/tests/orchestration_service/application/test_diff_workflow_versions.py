"""Unit tests for `diff_workflow_versions` — pure, zero I/O, no new
storage."""

from __future__ import annotations

from datetime import UTC, datetime

from agentverse_api.orchestration_service.application.diff_workflow_versions import (
    diff_workflow_versions,
)
from agentverse_api.orchestration_service.domain.workflow_entities import (
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeType,
    WorkflowVersion,
)

_NOW = datetime.now(UTC)


def _version(
    version_number: int, nodes: list[WorkflowNode], edges: list[WorkflowEdge]
) -> WorkflowVersion:
    return WorkflowVersion(
        id=f"v{version_number}",
        workflow_id="wf-1",
        version_number=version_number,
        nodes=nodes,
        edges=edges,
        created_by_user_id="user-1",
        created_at=_NOW,
    )


def _node(node_id: str, config: dict[str, object] | None = None) -> WorkflowNode:
    return WorkflowNode(
        id=node_id,
        type=WorkflowNodeType.PARALLEL_FANOUT,
        position_x=0,
        position_y=0,
        config=config or {},
    )


def test_identical_versions_have_no_diff() -> None:
    v1 = _version(1, [_node("a")], [])
    v2 = _version(2, [_node("a")], [])
    diff = diff_workflow_versions(v1, v2)
    assert diff.added_nodes == []
    assert diff.removed_nodes == []
    assert diff.changed_nodes == []
    assert diff.added_edges == []
    assert diff.removed_edges == []


def test_added_node_is_detected() -> None:
    v1 = _version(1, [_node("a")], [])
    v2 = _version(2, [_node("a"), _node("b")], [])
    diff = diff_workflow_versions(v1, v2)
    assert [n.id for n in diff.added_nodes] == ["b"]
    assert diff.removed_nodes == []


def test_removed_node_is_detected() -> None:
    v1 = _version(1, [_node("a"), _node("b")], [])
    v2 = _version(2, [_node("a")], [])
    diff = diff_workflow_versions(v1, v2)
    assert [n.id for n in diff.removed_nodes] == ["b"]
    assert diff.added_nodes == []


def test_changed_node_config_is_detected() -> None:
    v1 = _version(1, [_node("a", {"message": "before"})], [])
    v2 = _version(2, [_node("a", {"message": "after"})], [])
    diff = diff_workflow_versions(v1, v2)
    assert len(diff.changed_nodes) == 1
    before, after = diff.changed_nodes[0]
    assert before.config == {"message": "before"}
    assert after.config == {"message": "after"}
    assert diff.added_nodes == []
    assert diff.removed_nodes == []


def test_edge_additions_and_removals_are_detected() -> None:
    e1 = WorkflowEdge(id="e1", from_node_id="a", to_node_id="b")
    e2 = WorkflowEdge(id="e2", from_node_id="b", to_node_id="c")
    v1 = _version(1, [_node("a"), _node("b")], [e1])
    v2 = _version(2, [_node("a"), _node("b"), _node("c")], [e2])
    diff = diff_workflow_versions(v1, v2)
    assert [e.id for e in diff.added_edges] == ["e2"]
    assert [e.id for e in diff.removed_edges] == ["e1"]
