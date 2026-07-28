"""An SDK `MCPServer` with AgentVerse's tool-execution boundary inside
it.

This is the piece that makes "nothing bypasses the boundary" true rather
than aspirational.

The SDK owns tool dispatch: it lists an agent's `mcp_servers`, decides
which tool to call, and calls `server.call_tool(...)` itself. There is no
hook AgentVerse could place between those steps from the outside — so a
boundary that lived beside the SDK would govern native tools and silently
miss every MCP one, which is the larger surface.

So the boundary moves inside. `GovernedMcpServer` delegates connection,
naming, cleanup, and discovery straight to the SDK server it wraps, and
overrides exactly one method: `call_tool`, which runs the boundary around
the real call.

Delegation rather than subclassing the concrete transports, because the
three transports are separate classes and a mixin over each would be
three places for the governance to drift.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.types import CallToolResult, TextContent

from agents.agent import AgentBase
from agents.mcp import MCPServer
from agents.run_context import RunContextWrapper
from agentverse_worker.tools.boundary import (
    BoundaryDeps,
    ExecutionContext,
    ToolDefinition,
    ToolGrant,
    execute_tool,
)

logger = logging.getLogger(__name__)

#: Statuses the model should read as "this did not work", so the SDK
#: marks the result as an error and the agent can react.
_FAILED_STATUSES = frozenset({"error", "timeout", "denied", "circuit_open"})


class GovernedMcpServer(MCPServer):
    """Wraps one SDK MCP server so every tool call is governed.

    `tools_by_name` is the discovery result, needed because the boundary
    decides on the tool's *declared schema* and mutation classification —
    neither of which is available from the call arguments alone.

    A tool the server offers but discovery did not record is refused
    rather than passed through: it means the surface changed under us,
    and calling something whose schema we never validated is exactly what
    the boundary exists to prevent.
    """

    def __init__(
        self,
        inner: MCPServer,
        *,
        grant: ToolGrant,
        context: ExecutionContext,
        deps: BoundaryDeps,
        tools_by_name: dict[str, ToolDefinition],
        on_event: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__()
        self._inner = inner
        self._grant = grant
        self._context = context
        self._deps = deps
        self._tools = tools_by_name
        self._on_event = on_event

    # --- delegated, unchanged --------------------------------------------

    @property
    def name(self) -> str:
        return self._inner.name

    async def connect(self) -> None:
        await self._inner.connect()  # type: ignore[no-untyped-call]

    async def cleanup(self) -> None:
        await self._inner.cleanup()  # type: ignore[no-untyped-call]

    async def list_tools(
        self,
        run_context: RunContextWrapper[Any] | None = None,
        agent: AgentBase | None = None,
    ) -> list[Any]:
        """Discovery is the SDK's, including its own tool filter.

        Not re-filtered here: the allowed-tool list is already applied
        via the SDK's `create_static_tool_filter` at construction, and
        applying it twice in two different places is how the two answers
        eventually disagree.
        """
        return await self._inner.list_tools(run_context, agent)

    async def list_prompts(self) -> Any:
        """Prompts are read-only server content, not an action.

        Delegated rather than governed: listing prompts has no side
        effect and consumes no tool budget. The *content* is still
        untrusted — whatever uses a prompt must wrap it — but there is
        nothing here for the boundary to permit or deny.
        """
        return await self._inner.list_prompts()

    async def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        return await self._inner.get_prompt(name, arguments)

    # --- governed ---------------------------------------------------------

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
        meta: dict[str, Any] | None = None,
    ) -> CallToolResult:
        """Every MCP tool call, through the boundary.

        Returns a `CallToolResult` in all cases — including denials and
        failures — because raising here would end the run. The agent is
        told what happened and can choose a different approach, which is
        the behaviour the phase's acceptance criteria require of a
        failing server.
        """
        definition = self._tools.get(tool_name)
        if definition is None:
            # The server offered a tool discovery never recorded. Its
            # schema was never validated, so there is nothing to check
            # arguments against.
            reason = (
                f"tool {tool_name!r} was not present when this server's tools were "
                "discovered; its schema has not been validated"
            )
            await self._emit("mcp_tool_unknown", {"tool": tool_name, "reason": reason})
            return _error_result(f"This tool call was not permitted: {reason}")

        async def _invoke(args: dict[str, Any]) -> str:
            result = await self._inner.call_tool(tool_name, args, meta)
            if result.isError:
                # Surfaced as an exception so the boundary's retry and
                # circuit-breaker paths treat it as the failure it is —
                # returning it as content would make a broken server look
                # healthy to every policy above.
                raise McpToolError(_text_of(result) or "the tool reported an error")
            return _text_of(result)

        outcome = await execute_tool(
            tool=definition,
            arguments=arguments or {},
            grant=self._grant,
            context=self._context,
            invoke=_invoke,
            recorder=self._deps.recorder,
            breaker=self._deps.breaker,
            cache=self._deps.cache,
            budget=self._deps.budget,
        )

        await self._emit(
            "tool_call",
            {
                "server": self.name,
                "tool": tool_name,
                "status": outcome.status,
                "duration_ms": outcome.duration_ms,
                "denial_reason": outcome.denial_reason,
            },
        )

        return CallToolResult(
            content=[TextContent(type="text", text=outcome.content)],
            isError=outcome.status in _FAILED_STATUSES,
        )

    async def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        """Trace emission never breaks a tool call.

        The trace is how a user answers "what did my agent do"; losing an
        event is bad, but losing the tool call because the trace write
        failed is worse.
        """
        if self._on_event is None:
            return
        try:
            await self._on_event(event_type, payload)
        except Exception:  # noqa: BLE001 - a trace write must not fail the call
            logger.warning("mcp_trace_emit_failed event=%s", event_type)


class McpToolError(Exception):
    """An MCP server reported `isError` on a tool result.

    A distinct type so the boundary's retry logic can treat a server-side
    tool error the same as a transport failure — both mean "this call did
    not produce a usable result" — without swallowing programming errors
    from our own code.
    """


def _text_of(result: CallToolResult) -> str:
    """Flattens an MCP result's content blocks to text.

    Non-text blocks (images, embedded resources) are described rather
    than dropped: an agent told "[image]" knows something came back it
    cannot read, where silence looks like an empty result.
    """
    parts: list[str] = []
    for block in result.content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
        else:
            parts.append(f"[{getattr(block, 'type', 'unknown')} content]")
    return "\n".join(parts)


def _error_result(message: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=message)], isError=True)
