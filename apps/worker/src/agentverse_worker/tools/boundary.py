"""The central tool-execution boundary.

Every tool call in AgentVerse passes through `execute_tool` — native
built-ins, MCP-sourced tools, and SDK-wrapped tools alike. There is no
"trusted" fast path for first-party tools, deliberately: a bypass would
put holes in the audit log exactly where an investigator looks first, and
would create a second code path that drifts from the reviewed one
(ADR-0010, CLAUDE.md §4).

The order of operations is the design, and it is ordered by cost:

1. **Circuit breaker** — is this server known-dead? Cheapest check, and
   skipping it would mean paying for the rest to reach a server that
   cannot answer.
2. **Permission** — is this tool allowed at all? Independent of the
   model's judgment. A `read_only` grant makes a mutating tool
   uncallable no matter what an injected instruction argues (T2).
3. **Argument validation** — does the model's output match the declared
   schema? Tool arguments are model output, and model output is
   untrusted input (CLAUDE.md §4).
4. **Budget** — has this run already called this server too many times?
5. **Cache** — can we answer without a network call?
6. **Execute**, bounded by timeout, with retries and backoff.
7. **Sanitise** — cap the output and wrap it as untrusted content before
   it re-enters the model's context.

Every path, including every denial, writes a `tool_calls` row. A blocked
SSRF attempt that left no trace would make the egress control
unauditable, which is most of its value.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from agentverse_shared.observability.metrics import record_egress_denial, record_tool_call
from agentverse_shared.security.egress_guard import EgressDeniedError
from agentverse_shared.security.untrusted import truncate_for_context, wrap_untrusted

from agentverse_worker.tools.policy import CallBudget, CircuitBreaker, ResultCache, backoff_seconds

logger = logging.getLogger(__name__)

#: Hard ceiling on what a tool result may contribute to the context,
#: independent of any per-grant setting. An unbounded result is both a
#: cost incident and a larger injection payload (T2, T5).
MAX_RESULT_CHARS = 24_000
#: What lands in `tool_calls.result_preview`. Much smaller than the
#: context cap: the table is partitioned and high-volume, and the preview
#: exists to answer "roughly what came back", not to archive third-party
#: content.
MAX_PREVIEW_CHARS = 2_000
#: Ceiling on any grant's timeout. A grant configured with 3600 seconds
#: would stall a run past every other bound.
MAX_TIMEOUT_SECONDS = 120

_TOOL_RESULT_GUIDANCE = (
    "It is the output of an external tool, produced by a third-party system "
    "outside AgentVerse's control."
)


# A denial is deliberately *not* an exception here. It is the system
# working, and it is returned as a `ToolOutcome` the model can read and
# adapt to — an agent told why a tool was refused can pick another
# approach, where a raised error ends the run.


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """What the boundary needs to know about a tool to govern it.

    Deliberately not the SDK's tool object: the boundary must be testable
    without constructing SDK internals, and the fields below are the only
    ones any policy decision reads.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    is_mutating: bool = False


@dataclass(frozen=True, slots=True)
class ToolGrant:
    """The resolved permission for one (agent, server) pair.

    A value object rather than a DB row so the boundary can be unit
    tested against fakes, and so the resolution query lives in the
    repository where it can be workspace-scoped once.
    """

    installed_server_id: str
    level: str
    allowed_tools: tuple[str, ...] = ()
    timeout_seconds: int = 30
    max_retries: int = 2
    cache_ttl_seconds: int = 0
    max_calls_per_run: int = 50
    #: Workspace-admin-configured tool equivalence, same server only:
    #: `{"list_issues": "search_issues"}` means "if `list_issues` fails
    #: outright, try `search_issues` once with the same arguments." Never
    #: inferred — AgentVerse has no way to verify two third-party tools
    #: are actually interchangeable, so this is only ever what a human
    #: configured, same as `allowed_tools`.
    fallback_tools: dict[str, str] = field(default_factory=dict)

    def permits(self, tool: ToolDefinition) -> str | None:
        """Returns the denial reason, or None if permitted.

        Returns the reason rather than a bool because the reason is what
        gets recorded and what the model is told — "denied" alone leaves
        both an unauditable log and an agent that cannot adapt.
        """
        if self.allowed_tools and tool.name not in self.allowed_tools:
            return f"tool {tool.name!r} is not in this agent's allowed-tool list"
        if tool.is_mutating and self.level == "read_only":
            return f"tool {tool.name!r} modifies remote state and this agent has read-only access"
        return None


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    """The result of one governed call.

    `content` is always safe to hand back to the model: capped, wrapped,
    and labelled. A denial produces a `content` explaining the refusal
    rather than raising, so the agent can choose a different approach
    instead of the run dying.
    """

    status: str
    content: str
    duration_ms: int
    result_bytes: int | None = None
    denial_reason: str | None = None
    error_message: str | None = None
    attempts: int = 1
    #: Set when the tool actually invoked was a configured fallback, not
    #: the one the model asked for — the name of the original tool that
    #: failed. `None` means the model's own choice ran.
    substituted_from: str | None = None


class ToolCallRecorder(Protocol):
    """What the boundary writes to. A Protocol so the boundary is unit
    testable without Postgres (CLAUDE.md §11).
    """

    async def record_call(
        self,
        *,
        workspace_id: str,
        run_id: str | None,
        team_session_id: str | None,
        agent_id: str | None,
        installed_server_id: str | None,
        tool_name: str,
        status: str,
        arguments: dict[str, Any],
        result_preview: str | None,
        result_bytes: int | None,
        duration_ms: int | None,
        error_message: str | None,
        denial_reason: str | None,
        attempt: int,
    ) -> None: ...


@dataclass(slots=True)
class ExecutionContext:
    """Who is calling, and on whose behalf.

    `workspace_id` is required and threaded through every write, so a
    `tool_calls` row without tenancy is unexpressible (Rule 11).
    """

    workspace_id: str
    run_id: str | None = None
    team_session_id: str | None = None
    agent_id: str | None = None
    #: TTL for the per-run call budget counter, so it disappears with the
    #: run rather than needing a sweep.
    budget_ttl_seconds: int = 3600


def validate_arguments(arguments: dict[str, Any], schema: dict[str, Any]) -> str | None:
    """Checks model-supplied arguments against the declared JSON schema.

    Returns a denial reason, or None. Deliberately a narrow subset of
    JSON Schema — required properties, declared types, and
    `additionalProperties: false` — rather than a full validator.

    The reason is that this runs on every tool call in the hot path, and
    the properties that actually matter for security are these three: a
    missing required field, an argument of the wrong type, and an
    argument the tool never declared. A full JSON Schema implementation
    would add a dependency and a great deal of surface for the marginal
    cases; a tool needing deeper validation should validate server-side,
    which it must do anyway since it cannot trust us either.
    """
    if not isinstance(schema, dict):
        return None

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return None

    required = schema.get("required", [])
    if isinstance(required, list):
        missing = [name for name in required if name not in arguments]
        if missing:
            return f"missing required argument(s): {', '.join(sorted(missing))}"

    if schema.get("additionalProperties") is False:
        extra = [name for name in arguments if name not in properties]
        if extra:
            return f"unexpected argument(s): {', '.join(sorted(extra))}"

    type_map: dict[str, tuple[type, ...]] = {
        "string": (str,),
        "number": (int, float),
        "integer": (int,),
        "boolean": (bool,),
        "array": (list,),
        "object": (dict,),
    }
    for name, value in arguments.items():
        declared = properties.get(name)
        if not isinstance(declared, dict):
            continue
        expected = declared.get("type")
        if not isinstance(expected, str):
            continue
        allowed = type_map.get(expected)
        if allowed is None:
            continue
        # `bool` is a subclass of `int` in Python; a boolean passed where
        # an integer is declared would otherwise slip through.
        if expected in ("number", "integer") and isinstance(value, bool):
            return f"argument {name!r} must be {expected}, got boolean"
        if not isinstance(value, allowed):
            return f"argument {name!r} must be {expected}, got {type(value).__name__}"
    return None


def sanitize_result(raw: str) -> tuple[str, int]:
    """Caps a tool result and wraps it as untrusted content.

    Returns the wrapped text and the original byte length.

    This is the single place third-party output re-enters an LLM context,
    and it never returns bare text — a caller cannot accidentally
    concatenate an unwrapped result into instructions, because there is
    no unwrapped result to concatenate (T2).
    """
    result_bytes = len(raw.encode("utf-8"))
    capped, _ = truncate_for_context(raw, max_chars=MAX_RESULT_CHARS, label="tool result")
    return wrap_untrusted(capped, tag="tool_result", guidance=_TOOL_RESULT_GUIDANCE), result_bytes


async def execute_tool(
    *,
    tool: ToolDefinition,
    arguments: dict[str, Any],
    grant: ToolGrant,
    context: ExecutionContext,
    invoke: Callable[[dict[str, Any]], Awaitable[str]],
    recorder: ToolCallRecorder,
    breaker: CircuitBreaker,
    cache: ResultCache,
    budget: CallBudget,
    fallback: ToolDefinition | None = None,
    fallback_invoke: Callable[[dict[str, Any]], Awaitable[str]] | None = None,
) -> ToolOutcome:
    """The choke point. Nothing calls a tool without going through here.

    `invoke` is the actual call — an SDK MCP tool invocation, or a native
    tool's coroutine. Injected rather than constructed here so this
    module governs execution without knowing how any particular tool
    executes, and so it is testable without a live MCP server.

    `fallback`/`fallback_invoke` are the tool `grant.fallback_tools` names
    as the equivalent of `tool`, resolved by the caller (which has the
    server's discovered tool catalogue; this module does not). They are
    only ever attempted once, and only after `tool` itself has genuinely
    failed — never for a denial, and never against a server whose
    breaker just opened, since a fallback is still the same server.
    """
    server_id = grant.installed_server_id

    async def _attempt(
        current: ToolDefinition,
        current_invoke: Callable[[dict[str, Any]], Awaitable[str]],
        *,
        substituted_from: str | None,
    ) -> ToolOutcome:
        """Steps 2 through 7 for one (tool, invoke) pair.

        A plain function rather than closing over `tool`/`invoke`, so it
        runs once for the model's chosen tool and, if that fails outright,
        a second time for its configured fallback — each with its own
        timing, its own `tool_calls` row, and its own permission/argument/
        budget/cache checks, because a fallback is a different tool with
        its own schema and its own mutation classification.
        """
        started = time.monotonic()
        #: Wall-clock this attempt spent *not* executing boundary logic:
        #: time inside `current_invoke` (the third party's) plus time
        #: asleep in retry backoff (a deliberate wait, not slowness).
        #:
        #: Subtracted from the total to get boundary overhead, which is
        #: the split the latency budget is built on. Counting backoff as
        #: overhead would put an 8-second sleep into a histogram whose
        #: p95 budget is 25ms, and the resulting alert would fire on every
        #: retried call while saying "our code got slower" — which would
        #: be false.
        excluded_seconds = 0.0

        async def _record(
            outcome: ToolOutcome, *, denial_category: str | None = None
        ) -> ToolOutcome:
            # Metrics first, and never inside a try that the recorder
            # could skip: a `tool_calls` write failing is exactly when the
            # counter matters most.
            elapsed_seconds = time.monotonic() - started
            record_tool_call(
                status=outcome.status,
                duration_seconds=elapsed_seconds,
                overhead_seconds=elapsed_seconds - excluded_seconds,
                denial_reason=denial_category,
            )
            await recorder.record_call(
                workspace_id=context.workspace_id,
                run_id=context.run_id,
                team_session_id=context.team_session_id,
                agent_id=context.agent_id,
                installed_server_id=server_id,
                tool_name=current.name,
                status=outcome.status,
                arguments=arguments,
                result_preview=outcome.content[:MAX_PREVIEW_CHARS] if outcome.content else None,
                result_bytes=outcome.result_bytes,
                duration_ms=outcome.duration_ms,
                error_message=outcome.error_message,
                denial_reason=outcome.denial_reason,
                attempt=outcome.attempts,
            )
            return outcome

        def _elapsed() -> int:
            return int((time.monotonic() - started) * 1000)

        def _refusal(status: str, reason: str) -> ToolOutcome:
            """A denial the model can read and adapt to.

            Surfaced as content rather than raised: an agent told *why* a
            tool was refused can pick another approach, where an
            exception ends the run.
            """
            return ToolOutcome(
                status=status,
                content=f"This tool call was not permitted: {reason}",
                duration_ms=_elapsed(),
                denial_reason=reason,
                substituted_from=substituted_from,
            )

        # 2. Permission — independent of the model's judgment. A
        #    fallback is checked exactly like a directly-called tool: a
        #    read-only grant cannot fall through to a mutating tool any
        #    more than it could call one directly.
        denial = grant.permits(current)
        if denial is not None:
            return await _record(_refusal("denied", denial), denial_category="permission")

        # 3. Argument validation — model output is untrusted input, and a
        #    fallback reuses those same arguments verbatim; if they don't
        #    fit the fallback's own declared schema, there is no safe
        #    substitution to make, and this is refused rather than guessed.
        invalid = validate_arguments(arguments, current.input_schema)
        if invalid is not None:
            return await _record(_refusal("denied", invalid), denial_category="invalid_arguments")

        # 4. Per-run budget — bounds a tool loop earlier and more cheaply
        #    than the run's own step and cost ceilings would.
        if context.run_id is not None:
            within = await budget.consume(
                run_id=context.run_id,
                server_id=server_id,
                limit=grant.max_calls_per_run,
                ttl_seconds=context.budget_ttl_seconds,
            )
            if not within:
                return await _record(
                    _refusal(
                        "denied",
                        f"this run has already made {grant.max_calls_per_run} calls to this server",
                    ),
                    denial_category="budget_exceeded",
                )

        # 5. Cache — only ever populated from successful calls, so a
        #    transient failure never becomes sticky for the whole TTL.
        #    Keyed on `current.name`, so the fallback's cache entry is
        #    never confused with the tool it substituted for.
        if grant.cache_ttl_seconds > 0:
            cached = await cache.get(
                workspace_id=context.workspace_id,
                server_id=server_id,
                tool_name=current.name,
                arguments=arguments,
            )
            if cached is not None:
                return await _record(
                    ToolOutcome(
                        status="cached",
                        content=cached,
                        duration_ms=_elapsed(),
                        substituted_from=substituted_from,
                    )
                )

        # 6. Execute, bounded.
        timeout = min(max(1, grant.timeout_seconds), MAX_TIMEOUT_SECONDS)
        attempts = grant.max_retries + 1
        last_error: str | None = None

        for attempt in range(1, attempts + 1):
            attempt_started = time.monotonic()
            try:
                async with asyncio.timeout(timeout):
                    raw = await current_invoke(arguments)
            except TimeoutError:
                excluded_seconds += time.monotonic() - attempt_started
                last_error = f"the tool did not respond within {timeout}s"
                await breaker.record_failure(workspace_id=context.workspace_id, server_id=server_id)
            except EgressDeniedError as exc:
                # Not retried and not counted against the breaker: the
                # destination is not going to become permitted, and a
                # denial is the system working rather than the server
                # failing.
                #
                # The time spent getting here is *ours* — DNS resolution
                # and validation, no third party reached — so it is
                # deliberately not excluded from overhead. A guard that
                # became slow should show up as boundary overhead, since
                # that is the path a probing attacker exercises over and
                # over.
                record_egress_denial(exc.category)
                return await _record(_refusal("denied", exc.reason), denial_category="egress")
            except Exception as exc:  # noqa: BLE001 - translated into an outcome, never a crash
                excluded_seconds += time.monotonic() - attempt_started
                last_error = str(exc)
                logger.warning(
                    "tool_call_failed workspace_id=%s server_id=%s tool=%s attempt=%s",
                    context.workspace_id,
                    server_id,
                    current.name,
                    attempt,
                )
                await breaker.record_failure(workspace_id=context.workspace_id, server_id=server_id)
            else:
                excluded_seconds += time.monotonic() - attempt_started
                # 7. Sanitise before the result re-enters the model
                #    context.
                content, result_bytes = sanitize_result(raw)
                if substituted_from is not None:
                    content = (
                        f"[Automatically retried with '{current.name}' after "
                        f"'{substituted_from}' failed.]\n{content}"
                    )
                await breaker.record_success(workspace_id=context.workspace_id, server_id=server_id)
                if grant.cache_ttl_seconds > 0:
                    await cache.put(
                        workspace_id=context.workspace_id,
                        server_id=server_id,
                        tool_name=current.name,
                        arguments=arguments,
                        result=content,
                        ttl_seconds=grant.cache_ttl_seconds,
                    )
                return await _record(
                    ToolOutcome(
                        status="success",
                        content=content,
                        duration_ms=_elapsed(),
                        result_bytes=result_bytes,
                        attempts=attempt,
                        substituted_from=substituted_from,
                    )
                )

            if attempt < attempts:
                delay = backoff_seconds(attempt)
                await asyncio.sleep(delay)
                excluded_seconds += delay

        status = "timeout" if last_error and "did not respond" in last_error else "error"
        return await _record(
            ToolOutcome(
                status=status,
                # The model is told the tool failed, in terms it can act
                # on, rather than being handed a stack trace or nothing
                # at all.
                content=f"This tool call failed after {attempts} attempt(s): {last_error}",
                duration_ms=_elapsed(),
                error_message=last_error,
                attempts=attempts,
                substituted_from=substituted_from,
            )
        )

    # 1. Circuit breaker — cheapest check first, and shared: the
    #    fallback is the same server, so a known-dead server refuses both,
    #    and this check never runs a second time for the fallback tool.
    state = await breaker.state(workspace_id=context.workspace_id, server_id=server_id)
    if state.is_open:
        reason = (
            f"the server is temporarily unavailable after repeated failures; "
            f"retry in {state.retry_after_seconds}s"
        )
        outcome = ToolOutcome(
            status="circuit_open",
            content=f"This tool call was not permitted: {reason}",
            duration_ms=0,
            denial_reason=reason,
        )
        record_tool_call(
            status=outcome.status,
            duration_seconds=0.0,
            overhead_seconds=0.0,
            denial_reason="circuit_open",
        )
        await recorder.record_call(
            workspace_id=context.workspace_id,
            run_id=context.run_id,
            team_session_id=context.team_session_id,
            agent_id=context.agent_id,
            installed_server_id=server_id,
            tool_name=tool.name,
            status=outcome.status,
            arguments=arguments,
            result_preview=None,
            result_bytes=None,
            duration_ms=outcome.duration_ms,
            error_message=None,
            denial_reason=outcome.denial_reason,
            attempt=outcome.attempts,
        )
        return outcome

    outcome = await _attempt(tool, invoke, substituted_from=None)

    if (
        outcome.status in ("error", "timeout")
        and fallback is not None
        and fallback_invoke is not None
    ):
        # Re-check rather than assume: the failure just recorded above
        # may itself have been the one that opened the breaker, and
        # burning a fallback call against a server just confirmed dead
        # defeats the point of having a breaker at all.
        post_failure_state = await breaker.state(
            workspace_id=context.workspace_id, server_id=server_id
        )
        if not post_failure_state.is_open:
            return await _attempt(fallback, fallback_invoke, substituted_from=tool.name)

    return outcome


@dataclass(slots=True)
class BoundaryDeps:
    """The collaborators `execute_tool` needs, bundled.

    Exists so call sites pass one object instead of five, without making
    `execute_tool` itself a class — the function has no state between
    calls and turning it into a method would imply it does.
    """

    recorder: ToolCallRecorder
    breaker: CircuitBreaker
    cache: ResultCache
    budget: CallBudget
    extras: dict[str, Any] = field(default_factory=dict)
