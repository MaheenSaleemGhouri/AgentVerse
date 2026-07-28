"""Attaches resolved MCP integrations to an SDK `Agent`.

One function, called from both the single-agent run path and the team
member factory, because the rule they must both obey is the same and a
second copy would eventually only be right in one of them:

**A failing MCP server disables only its own tools for that run, with a
clear trace event — it never crashes the agent run.** (Phase acceptance
criteria; `mcp-expert` operating principle 5.)

Every server that connects is wrapped in `GovernedMcpServer`, so the
`Agent` never holds a raw SDK server object. That is what makes "no tool
call bypasses the boundary" a structural property rather than a
convention someone has to remember.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from agents.mcp import MCPServer
from agentverse_worker.mcp.governed import GovernedMcpServer
from agentverse_worker.mcp.manager import McpConnectionManager
from agentverse_worker.mcp.repository import ResolvedIntegration
from agentverse_worker.tools.boundary import BoundaryDeps, ExecutionContext

logger = logging.getLogger(__name__)

#: Cap on how many servers one agent may attach. Each is a live
#: connection and a block of tool descriptions in the prompt; past a
#: handful, tool selection degrades and the context bill grows for tools
#: the model will never pick.
MAX_ATTACHED_SERVERS = 10


@dataclass(slots=True)
class AttachmentResult:
    """What ended up attached, and what did not.

    `unavailable` is deliberately part of the return value rather than
    only a log line: the caller emits it as a trace event, so a user
    looking at a run that "ignored my GitHub tools" gets an answer
    instead of silence.
    """

    servers: list[MCPServer] = field(default_factory=list)
    #: `(display_name, reason)` for each server that could not be used.
    unavailable: list[tuple[str, str]] = field(default_factory=list)
    manager: McpConnectionManager | None = None

    @property
    def attached_count(self) -> int:
        return len(self.servers)


async def attach_integrations(
    integrations: list[ResolvedIntegration],
    *,
    context: ExecutionContext,
    deps: BoundaryDeps,
    on_event: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
) -> AttachmentResult:
    """Connects to each integration and returns governed servers.

    The caller owns the returned `manager` and must close it — the
    connections outlive this function because the `Agent` uses them for
    the duration of the run.

    Never raises for a server-side problem. A connection failure becomes
    an `unavailable` entry, and the run proceeds with whatever connected.
    """
    result = AttachmentResult()
    if not integrations:
        return result

    if len(integrations) > MAX_ATTACHED_SERVERS:
        # Truncated rather than refused: an agent granted eleven servers
        # should still run, and the trace says which were dropped.
        dropped = integrations[MAX_ATTACHED_SERVERS:]
        integrations = integrations[:MAX_ATTACHED_SERVERS]
        for integration in dropped:
            result.unavailable.append(
                (
                    integration.spec.display_name,
                    f"more than {MAX_ATTACHED_SERVERS} servers are attached to this agent",
                )
            )

    manager = McpConnectionManager()
    result.manager = manager

    connections = await manager.connect_all([i.spec for i in integrations])
    by_id = {i.spec.installed_server_id: i for i in integrations}

    for connection in connections:
        resolved = by_id.get(connection.installed_server_id)
        if resolved is None:  # pragma: no cover - defensive
            continue

        if not connection.is_usable or connection.server is None:
            reason = connection.error or "unavailable"
            result.unavailable.append((connection.display_name, reason))
            logger.info(
                "mcp_server_unavailable workspace_id=%s server_id=%s",
                context.workspace_id,
                connection.installed_server_id,
            )
            if on_event is not None:
                await on_event(
                    "mcp_server_unavailable",
                    {
                        "server": connection.display_name,
                        "installed_server_id": connection.installed_server_id,
                        "reason": reason,
                    },
                )
            continue

        # Prefer the freshly discovered tool surface over the cached one:
        # a schema that changed since install must be validated against
        # what the server actually offers now, not what it used to.
        tools = {tool.name: _as_definition(tool) for tool in connection.tools} or resolved.tools

        result.servers.append(
            GovernedMcpServer(
                connection.server,
                grant=resolved.grant,
                context=context,
                deps=deps,
                tools_by_name=tools,
                on_event=on_event,
            )
        )
        if on_event is not None:
            await on_event(
                "mcp_server_attached",
                {
                    "server": connection.display_name,
                    "installed_server_id": connection.installed_server_id,
                    "tool_count": len(tools),
                },
            )

    return result


def _as_definition(tool: Any) -> Any:
    """Adapts a `DiscoveredTool` to the boundary's `ToolDefinition`.

    Two near-identical types on purpose: `DiscoveredTool` belongs to the
    MCP layer and `ToolDefinition` to the boundary, which governs native
    tools too and must not import an MCP type to do it.
    """
    from agentverse_worker.tools.boundary import ToolDefinition

    return ToolDefinition(
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema,
        is_mutating=tool.is_mutating,
    )
