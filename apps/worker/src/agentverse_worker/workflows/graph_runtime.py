"""Pure DAG-execution helpers — zero I/O, unit-tested directly
(CLAUDE.md §11). `workflow_node_job.py` is the only caller; kept
separate so the templating/branching rules are testable without a
Postgres session or the Agents SDK in the loop.
"""

from __future__ import annotations

import re
from typing import Any

from agentverse_worker.workflows.repository import WorkflowEdgeRecord

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_.\-]+)\s*\}\}")

#: Used when a node's config carries no `input_template` key.
DEFAULT_INPUT_TEMPLATE = "{{trigger.input}}"


def resolve_input_template(
    template: str, *, trigger_input: str, node_outputs: dict[str, str]
) -> str:
    """`{{trigger.input}}` substitutes the workflow run's own trigger
    prompt; `{{nodes.<node_id>.output}}` substitutes that node's text
    output. An unrecognized placeholder is left untouched rather than
    raising — a typo'd reference degrades to literal text in the
    prompt, visible in the trace, rather than failing the whole run.
    """

    def _substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        if key == "trigger.input":
            return trigger_input
        if key.startswith("nodes.") and key.endswith(".output"):
            node_id = key[len("nodes.") : -len(".output")]
            return node_outputs.get(node_id, "")
        return match.group(0)

    return _PLACEHOLDER.sub(_substitute, template)


def evaluate_condition(condition: dict[str, Any] | None, output: dict[str, Any] | None) -> bool:
    """A simple field/operator/value comparison — no expression
    language. `condition=None` is the default/else edge, and always
    matches (used only when no sibling edge's condition matched first).
    """
    if condition is None:
        return True
    if output is None:
        return False
    field = condition.get("field")
    operator = condition.get("operator", "equals")
    expected = condition.get("value")
    actual = output.get(field) if field else None
    if operator == "equals":
        return bool(actual == expected)
    if operator == "not_equals":
        return bool(actual != expected)
    if operator == "contains":
        return isinstance(actual, str) and isinstance(expected, str) and expected in actual
    return False


def ordered_outgoing_edges(
    edges: list[WorkflowEdgeRecord], *, from_node_id: str
) -> list[WorkflowEdgeRecord]:
    """Explicit `branch_order` first (ascending), the `condition=None`
    default/else edge evaluated last — mirrors `WorkflowVersion.
    outgoing_edges` on the API side (domain entity, not reachable from
    the worker), kept in lockstep as a documented wire-contract rule
    rather than shared code (CLAUDE.md §5).
    """
    matching = [e for e in edges if e.from_node_id == from_node_id]
    return sorted(matching, key=lambda e: (e.branch_order is None, e.branch_order or 0))
