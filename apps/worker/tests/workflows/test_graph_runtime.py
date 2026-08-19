"""Unit tests for the pure DAG-execution helpers — zero I/O."""

from __future__ import annotations

from agentverse_worker.workflows.graph_runtime import (
    evaluate_condition,
    ordered_outgoing_edges,
    resolve_input_template,
)
from agentverse_worker.workflows.repository import WorkflowEdgeRecord


def test_trigger_input_placeholder_is_substituted() -> None:
    result = resolve_input_template(
        "Summarize: {{trigger.input}}", trigger_input="hello world", node_outputs={}
    )
    assert result == "Summarize: hello world"


def test_node_output_placeholder_is_substituted() -> None:
    result = resolve_input_template(
        "Given {{nodes.n1.output}}, decide next.",
        trigger_input="",
        node_outputs={"n1": "category: billing"},
    )
    assert result == "Given category: billing, decide next."


def test_unrecognized_placeholder_is_left_untouched() -> None:
    result = resolve_input_template(
        "See {{nodes.missing.output}}", trigger_input="", node_outputs={}
    )
    assert result == "See "


def test_placeholder_referencing_unknown_typo_is_left_literal() -> None:
    result = resolve_input_template("{{unknown.thing}}", trigger_input="x", node_outputs={})
    assert result == "{{unknown.thing}}"


def test_condition_none_is_the_default_edge_and_always_matches() -> None:
    assert evaluate_condition(None, {"text": "anything"}) is True
    assert evaluate_condition(None, None) is True


def test_equals_condition() -> None:
    condition = {"field": "text", "operator": "equals", "value": "billing"}
    assert evaluate_condition(condition, {"text": "billing"}) is True
    assert evaluate_condition(condition, {"text": "support"}) is False


def test_contains_condition() -> None:
    condition = {"field": "text", "operator": "contains", "value": "urgent"}
    assert evaluate_condition(condition, {"text": "this is urgent, help"}) is True
    assert evaluate_condition(condition, {"text": "not a priority"}) is False


def test_not_equals_condition() -> None:
    condition = {"field": "text", "operator": "not_equals", "value": "billing"}
    assert evaluate_condition(condition, {"text": "support"}) is True
    assert evaluate_condition(condition, {"text": "billing"}) is False


def test_condition_against_missing_output_never_matches() -> None:
    condition = {"field": "text", "operator": "equals", "value": "billing"}
    assert evaluate_condition(condition, None) is False


def test_ordered_outgoing_edges_puts_explicit_branch_order_first_then_default_last() -> None:
    edges = [
        WorkflowEdgeRecord(
            id="e-default", from_node_id="n1", to_node_id="c", condition=None, branch_order=None
        ),
        WorkflowEdgeRecord(
            id="e2", from_node_id="n1", to_node_id="b", condition={}, branch_order=2
        ),
        WorkflowEdgeRecord(
            id="e1", from_node_id="n1", to_node_id="a", condition={}, branch_order=1
        ),
        WorkflowEdgeRecord(
            id="e-other", from_node_id="n2", to_node_id="z", condition=None, branch_order=None
        ),
    ]
    ordered = ordered_outgoing_edges(edges, from_node_id="n1")
    assert [e.id for e in ordered] == ["e1", "e2", "e-default"]
