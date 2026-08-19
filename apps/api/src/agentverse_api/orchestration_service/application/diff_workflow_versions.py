"""Pure diff between two workflow versions — no new storage, computed at
request time (CLAUDE.md §11: pure functions, zero I/O). Rollback and
version comparison in the builder both consume this, not a stored diff.
"""

from __future__ import annotations

from agentverse_api.orchestration_service.domain.workflow_entities import (
    WorkflowNode,
    WorkflowVersion,
    WorkflowVersionDiff,
)


def diff_workflow_versions(
    from_version: WorkflowVersion, to_version: WorkflowVersion
) -> WorkflowVersionDiff:
    from_nodes = {n.id: n for n in from_version.nodes}
    to_nodes = {n.id: n for n in to_version.nodes}
    from_edges = {e.id: e for e in from_version.edges}
    to_edges = {e.id: e for e in to_version.edges}

    added_nodes = [n for nid, n in to_nodes.items() if nid not in from_nodes]
    removed_nodes = [n for nid, n in from_nodes.items() if nid not in to_nodes]
    changed_nodes = [
        (from_nodes[nid], to_nodes[nid])
        for nid in from_nodes.keys() & to_nodes.keys()
        if _node_changed(from_nodes[nid], to_nodes[nid])
    ]

    added_edges = [e for eid, e in to_edges.items() if eid not in from_edges]
    removed_edges = [e for eid, e in from_edges.items() if eid not in to_edges]

    return WorkflowVersionDiff(
        added_nodes=added_nodes,
        removed_nodes=removed_nodes,
        changed_nodes=changed_nodes,
        added_edges=added_edges,
        removed_edges=removed_edges,
    )


def _node_changed(before: WorkflowNode, after: WorkflowNode) -> bool:
    return (
        before.type != after.type
        or before.config != after.config
        or before.agent_id != after.agent_id
        or before.team_id != after.team_id
    )
