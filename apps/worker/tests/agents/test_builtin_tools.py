"""`_safe_eval` is the safety-critical piece here (CLAUDE.md §7:
tool-call arguments returned by the model are untrusted input) — these
tests assert it only ever does arithmetic, never arbitrary code
execution, regardless of what a model hands it.
"""

from __future__ import annotations

import ast

import pytest

from agentverse_worker.agents.builtin_tools import _safe_eval, resolve_tools


def _eval(expr: str) -> float:
    return _safe_eval(ast.parse(expr, mode="eval").body)


def test_safe_eval_basic_arithmetic() -> None:
    assert _eval("2 + 2") == 4
    assert _eval("10 - 3") == 7
    assert _eval("4 * 5") == 20
    assert _eval("9 / 2") == 4.5
    assert _eval("-5") == -5
    assert _eval("(2 + 3) * 4") == 20


def test_safe_eval_rejects_non_arithmetic_nodes() -> None:
    # Function calls, attribute access, names — anything that isn't a
    # bare arithmetic expression must be rejected, not silently ignored.
    for expr in ["__import__('os').system('echo hi')", "open('/etc/passwd')", "a + 1", "[1,2,3]"]:
        with pytest.raises((ValueError, SyntaxError)):
            _eval(expr)


def test_resolve_tools_returns_known_tools_and_drops_unknown() -> None:
    tools = resolve_tools(["get_current_time", "calculator", "not_a_real_tool"])
    assert len(tools) == 2


def test_resolve_tools_empty_list_returns_empty() -> None:
    assert resolve_tools([]) == []
