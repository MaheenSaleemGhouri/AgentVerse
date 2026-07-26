"""A fixed, trusted set of demo function tools proving "single-agent-
with-tools" (docs/roadmap.md Phase 4) via the Agents SDK's own
`@function_tool` decorator — no custom tool-calling loop is built, the
SDK owns dispatch entirely.

This is deliberately NOT the formal central tool-execution boundary
(auth, logging, rate-limiting for arbitrary/dynamic tools) — that is
Phase 6's named deliverable. Until it exists, an agent's `tools` list
may only reference this fixed, built-in, trusted set; there is no path
for a user-supplied or dynamic tool to reach an agent yet.
"""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from datetime import UTC, datetime

from agents import FunctionTool, Tool, function_tool

_BINARY_OPERATORS: dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY_OPERATORS: dict[type, Callable[[float], float]] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST) -> float:
    """Evaluates a restricted arithmetic AST (numbers, + - * / and unary
    +/- only) — never Python's own `eval`, which would execute arbitrary
    code from model-supplied input (CLAUDE.md §7: tool-call arguments
    returned by the model are untrusted input).
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        return _BINARY_OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


@function_tool
async def get_current_time() -> str:
    """Returns the current UTC time as an ISO 8601 string."""
    return datetime.now(UTC).isoformat()


@function_tool
async def calculator(expression: str) -> str:
    """Evaluates a basic arithmetic expression (+, -, *, /, parentheses).

    Args:
        expression: The arithmetic expression to evaluate, e.g. "2 + 2 * 3".
    """
    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree.body)
    except Exception as exc:
        return f"error: could not evaluate expression ({exc})"
    return str(result)


_BUILTIN_TOOLS: dict[str, FunctionTool] = {
    "get_current_time": get_current_time,
    "calculator": calculator,
}


def resolve_tools(tool_names: list[str]) -> list[Tool]:
    """Silently drops any name outside the fixed built-in set rather than
    raising — an agent config saved before a tool was removed from this
    set should not fail to run, it should just run with fewer tools.

    Returns `list[Tool]` (the SDK's own broader union), not
    `list[FunctionTool]` — `Agent.tools` expects the former, and list
    covariance means a `list[FunctionTool]` doesn't structurally satisfy
    it even though every element does.
    """
    return [_BUILTIN_TOOLS[name] for name in tool_names if name in _BUILTIN_TOOLS]
