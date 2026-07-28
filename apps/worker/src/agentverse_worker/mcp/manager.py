"""Connection lifecycle, tool discovery, and health for MCP servers.

Wraps the SDK's connection objects with the things a multi-tenant
platform needs and the SDK does not provide: connections scoped to a
workspace, a failing server degrading to *its own* tools being
unavailable rather than the run dying, and a health signal the
marketplace can render.

The central rule, from `mcp-expert` and the phase's acceptance criteria:
**a disconnected or erroring MCP server disables only its own tools for
that run, with a clear trace event — it never crashes the agent run.**
Every method here is written to make that the easy path.

Connections are per-run, not pooled across runs. A pooled MCP session
would outlive the credential that opened it, and a revoked token would
keep working until the pool happened to evict the entry. Per-run costs a
handshake; the alternative costs correctness.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from agentverse_shared.security.egress_guard import EgressDeniedError

from agents.mcp import MCPServer
from agentverse_worker.mcp.factory import (
    ServerConnectionSpec,
    TransportNotPermittedError,
    build_server,
)

logger = logging.getLogger(__name__)

#: Ceiling on a single connect + discover. Independent of the tool-call
#: timeout: a server can be quick to answer tools and slow to hand shake,
#: and a run should not spend its budget on the latter.
CONNECT_TIMEOUT_SECONDS = 25.0

#: How long a discovered tool list stays fresh. Days would be defensible
#: — tool surfaces change rarely — but an hour means a user who adds a
#: tool on the remote side sees it within one, without a manual refresh.
DISCOVERY_TTL_SECONDS = 3600


@dataclass(frozen=True, slots=True)
class DiscoveredTool:
    """One tool as advertised, normalised away from the SDK's own type.

    Normalised because the rest of AgentVerse — the permission check, the
    boundary, the API response, the install screen — should not depend on
    the pinned SDK version's tool object shape.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    #: Inferred, not declared: MCP has no "this mutates" flag, so this is
    #: AgentVerse's own reading of the tool. See `infer_is_mutating`.
    is_mutating: bool


@dataclass(slots=True)
class ConnectionResult:
    """What happened when we tried to reach one server.

    Carries a failure rather than raising, because the caller's correct
    response to one dead server is to continue without its tools — and a
    result object makes that the obvious thing to write.
    """

    installed_server_id: str
    display_name: str
    server: MCPServer | None
    tools: list[DiscoveredTool] = field(default_factory=list)
    health: str = "unknown"
    error: str | None = None

    @property
    def is_usable(self) -> bool:
        return self.server is not None and self.error is None


#: Verbs that indicate a tool changes remote state. Used to decide
#: whether a `read_only` grant may call it.
#:
#: This is a heuristic, and it is deliberately biased toward *over*-
#: classifying: a read tool wrongly marked mutating is an annoyance a
#: user fixes by granting read-write, while a write tool wrongly marked
#: read-only is a read-only grant that can modify a customer's GitHub.
#: The failure directions are not symmetric, so neither is the default.
_MUTATING_PREFIXES = (
    "create",
    "update",
    "delete",
    "remove",
    "write",
    "put",
    "post",
    "patch",
    "set",
    "add",
    "insert",
    "send",
    "publish",
    "merge",
    "close",
    "assign",
    "upload",
    "move",
    "rename",
    "archive",
    "revoke",
    "grant",
    "execute",
    "run",
    "trigger",
    "cancel",
    "approve",
    "reject",
    "invite",
    "drop",
    "truncate",
    "modify",
    "edit",
    "push",
)

#: Read verbs that would otherwise trip a prefix above (`get_...` is
#: fine, but `list_...` and `search_...` never mutate).
_READ_PREFIXES = ("get", "list", "search", "read", "fetch", "query", "find", "describe", "show")


def infer_is_mutating(name: str, description: str) -> bool:
    """Best-effort read of whether a tool changes remote state.

    MCP tools do not declare this, so it has to be inferred, and an
    inference is exactly as trustworthy as its bias. Unknown tools
    default to **mutating**: a read-only grant that silently permits an
    unrecognised tool is the failure that matters, and a user can always
    widen the grant.
    """
    lowered = name.lower().strip()
    head = lowered.split("_", 1)[0].split("-", 1)[0]

    if head in _READ_PREFIXES:
        return False
    if head in _MUTATING_PREFIXES:
        return True

    # Anything unrecognised is treated as mutating. The description is
    # deliberately *not* consulted as a tiebreaker: it is written by the
    # server, so a malicious one would simply describe its write tool in
    # read-sounding language, and a signal an attacker controls cannot be
    # used to widen access.
    del description
    return True


def normalise_tools(raw_tools: list[Any]) -> list[DiscoveredTool]:
    """Maps SDK/MCP tool objects into AgentVerse's own representation.

    Defensive about shape: the tool object belongs to the pinned SDK
    version, and a changed attribute must degrade to a tool with a thin
    description rather than crash discovery for the whole server.
    """
    tools: list[DiscoveredTool] = []
    for raw in raw_tools:
        name = getattr(raw, "name", None)
        if not isinstance(name, str) or not name:
            continue
        description = getattr(raw, "description", None) or ""
        schema = getattr(raw, "inputSchema", None) or getattr(raw, "input_schema", None) or {}
        if not isinstance(schema, dict):
            schema = {}
        tools.append(
            DiscoveredTool(
                name=name,
                description=str(description),
                input_schema=schema,
                is_mutating=infer_is_mutating(name, str(description)),
            )
        )
    return tools


class McpConnectionManager:
    """Opens, discovers against, and closes MCP connections for one run.

    Holds the open connections so they can all be cleaned up together —
    an MCP session leaked when a run ends is a process (stdio) or a
    socket (HTTP) that outlives the thing that needed it.
    """

    def __init__(self) -> None:
        self._open: list[MCPServer] = []

    async def connect(self, spec: ServerConnectionSpec) -> ConnectionResult:
        """Connects to one server and discovers its tools.

        Never raises for a server-side problem. Every failure mode —
        denied endpoint, refused transport, timeout, protocol error —
        becomes a `ConnectionResult` carrying the reason, because the
        caller's correct response is always the same: continue without
        this server's tools and record why.
        """
        result = ConnectionResult(
            installed_server_id=spec.installed_server_id,
            display_name=spec.display_name,
            server=None,
        )
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT_SECONDS):
                server = await build_server(spec)
                # The SDK's own lifecycle methods are untyped; the
                # ignores are on the call, not a blanket module setting,
                # so a future typed SDK release surfaces here.
                await server.connect()  # type: ignore[no-untyped-call]
                self._open.append(server)
                raw_tools = await server.list_tools()
        except EgressDeniedError as exc:
            result.health = "unreachable"
            result.error = f"endpoint not permitted: {exc.reason}"
        except TransportNotPermittedError as exc:
            result.health = "unreachable"
            result.error = str(exc)
        except TimeoutError:
            result.health = "unreachable"
            result.error = f"did not respond within {CONNECT_TIMEOUT_SECONDS:.0f}s"
        except Exception as exc:  # noqa: BLE001 - a bad server must not kill the run
            logger.warning(
                "mcp_connect_failed workspace_id=%s server_id=%s",
                spec.workspace_id,
                spec.installed_server_id,
            )
            result.health = "unreachable"
            result.error = str(exc)
        else:
            result.server = server
            result.tools = normalise_tools(list(raw_tools))
            result.health = "healthy" if result.tools else "degraded"
            if not result.tools:
                # Connected but advertising nothing. Not an error — some
                # servers gate their tool list behind auth — but a user
                # staring at an empty tool picker deserves the reason.
                result.error = "connected, but the server advertised no tools"
        return result

    async def connect_all(self, specs: list[ServerConnectionSpec]) -> list[ConnectionResult]:
        """Connects to every server concurrently.

        Concurrent because a run attaching four servers should pay one
        handshake in wall-clock, not four. `return_exceptions` is not
        needed — `connect` already converts every failure into a result —
        but the gather is still per-spec so one slow server delays only
        itself.
        """
        if not specs:
            return []
        return list(await asyncio.gather(*(self.connect(spec) for spec in specs)))

    async def aclose(self) -> None:
        """Closes every open connection.

        Failures are logged and swallowed: this runs in a `finally`, and
        an exception here would replace whatever real outcome the run
        had with a cleanup error.
        """
        for server in self._open:
            try:
                await server.cleanup()  # type: ignore[no-untyped-call]
            except Exception:  # noqa: BLE001 - cleanup must not mask the run's outcome
                logger.warning("mcp_cleanup_failed name=%s", getattr(server, "name", "?"))
        self._open.clear()

    async def __aenter__(self) -> McpConnectionManager:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()


@dataclass(frozen=True, slots=True)
class HealthReport:
    installed_server_id: str
    health: str
    tool_count: int
    latency_ms: int | None
    error: str | None
    checked_at: datetime


async def check_health(spec: ServerConnectionSpec) -> HealthReport:
    """One-shot connect, discover, disconnect — for the health monitor.

    Deliberately opens and closes its own connection rather than reusing
    a run's: a health check that borrowed a live session would report the
    session's health, not the server's, and would say nothing at all when
    no run happened to be in flight.
    """
    started = datetime.now(UTC)
    manager = McpConnectionManager()
    try:
        result = await manager.connect(spec)
        latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        return HealthReport(
            installed_server_id=spec.installed_server_id,
            health=result.health,
            tool_count=len(result.tools),
            latency_ms=latency_ms,
            error=result.error,
            checked_at=started,
        )
    finally:
        await manager.aclose()


def diff_tool_surface(previous: list[DiscoveredTool], current: list[DiscoveredTool]) -> list[str]:
    """Names the tools whose surface changed between two discoveries.

    A breaking schema change on the server side is otherwise a silent
    runtime failure — the agent calls a tool that no longer accepts what
    it sends, and nothing says why (`mcp-expert`). Recorded per
    `server_versions` row so the change is visible after the fact.
    """
    before = {tool.name: tool for tool in previous}
    after = {tool.name: tool for tool in current}

    changed = [name for name in before.keys() - after.keys()]
    changed += [name for name in after.keys() - before.keys()]
    changed += [
        name
        for name in before.keys() & after.keys()
        if before[name].input_schema != after[name].input_schema
    ]
    return sorted(set(changed))
