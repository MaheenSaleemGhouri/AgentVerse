"""The boundary emits the metrics the monitoring doc alerts on.

Kept separate from `test_boundary.py` because the claims are different:
that file proves the boundary *governs* a call correctly, this one
proves the governing is visible. An egress denial that is blocked
perfectly and counted nowhere still means nobody finds out.

These read the global Prometheus registry, so every assertion is a
delta against a value sampled before the call rather than an absolute —
test order must not matter (CLAUDE.md §11).
"""

from __future__ import annotations

from typing import Any

import pytest
from agentverse_shared.security.egress_guard import EgressDeniedError
from fakeredis.aioredis import FakeRedis
from prometheus_client import REGISTRY

from agentverse_worker.tools.boundary import (
    ExecutionContext,
    ToolDefinition,
    ToolGrant,
    execute_tool,
)
from agentverse_worker.tools.policy import CallBudget, CircuitBreaker, ResultCache

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"repo": {"type": "string"}},
    "required": ["repo"],
    "additionalProperties": False,
}

READ_TOOL = ToolDefinition(
    name="list_issues", description="Lists issues.", input_schema=SCHEMA, is_mutating=False
)
WRITE_TOOL = ToolDefinition(
    name="create_issue", description="Creates an issue.", input_schema=SCHEMA, is_mutating=True
)


class FakeRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def record_call(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


@pytest.fixture
async def redis() -> Any:
    client = FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


def _value(name: str, **labels: str) -> float:
    got = REGISTRY.get_sample_value(name, labels or None)
    return 0.0 if got is None else got


async def _run(
    redis: Any,
    *,
    tool: ToolDefinition = READ_TOOL,
    arguments: dict[str, Any] | None = None,
    grant: ToolGrant | None = None,
    invoke: Any = None,
) -> Any:
    async def _default(_: dict[str, Any]) -> str:
        return "three issues found"

    return await execute_tool(
        tool=tool,
        arguments=arguments if arguments is not None else {"repo": "agentverse"},
        grant=grant or ToolGrant(installed_server_id="srv-1", level="read_write"),
        context=ExecutionContext(workspace_id="ws-1", run_id="run-1", agent_id="a-1"),
        invoke=invoke or _default,
        recorder=FakeRecorder(),
        breaker=CircuitBreaker(redis),
        cache=ResultCache(redis),
        budget=CallBudget(redis),
    )


async def test_a_successful_call_is_counted(redis: Any) -> None:
    before = _value("agentverse_tool_calls_total", status="success")

    await _run(redis)

    assert _value("agentverse_tool_calls_total", status="success") == before + 1


async def test_a_permission_denial_is_counted_under_permission(redis: Any) -> None:
    before = _value("agentverse_tool_calls_denied_total", reason="permission")

    outcome = await _run(
        redis,
        tool=WRITE_TOOL,
        grant=ToolGrant(installed_server_id="srv-1", level="read_only"),
    )

    assert outcome.status == "denied"
    assert _value("agentverse_tool_calls_denied_total", reason="permission") == before + 1


async def test_an_invalid_argument_is_counted_separately_from_a_permission_denial(
    redis: Any,
) -> None:
    """Both are `status="denied"`.

    If they shared a reason label, "the model keeps producing malformed
    arguments" and "an agent is repeatedly reaching for tools it may not
    use" would be the same line on the dashboard — and only the second
    is a security signal.
    """
    before = _value("agentverse_tool_calls_denied_total", reason="invalid_arguments")

    await _run(redis, arguments={"repo": "x", "shell": "rm -rf /"})

    assert _value("agentverse_tool_calls_denied_total", reason="invalid_arguments") == before + 1


async def test_a_budget_denial_is_counted_under_budget(redis: Any) -> None:
    grant = ToolGrant(installed_server_id="srv-budget", level="read_write", max_calls_per_run=1)
    before = _value("agentverse_tool_calls_denied_total", reason="budget_exceeded")

    await _run(redis, grant=grant)
    await _run(redis, grant=grant)

    assert _value("agentverse_tool_calls_denied_total", reason="budget_exceeded") == before + 1


async def test_an_egress_denial_is_counted_by_range(redis: Any) -> None:
    """The metric this whole surface exists for.

    A tool whose call resolves to the cloud metadata address is a
    credential-theft attempt. It is blocked either way — this asserts
    somebody would find out.
    """
    metadata_before = _value("agentverse_egress_denied_total", range="metadata")
    reason_before = _value("agentverse_tool_calls_denied_total", reason="egress")

    async def _blocked(_: dict[str, Any]) -> str:
        raise EgressDeniedError(
            "'evil.example' → destination 169.254.169.254 is in denied range 169.254.0.0/16",
            category="metadata",
        )

    outcome = await _run(redis, invoke=_blocked)

    assert outcome.status == "denied"
    assert _value("agentverse_egress_denied_total", range="metadata") == metadata_before + 1
    assert _value("agentverse_tool_calls_denied_total", reason="egress") == reason_before + 1


async def test_an_egress_denial_does_not_count_as_a_server_failure(redis: Any) -> None:
    """A refused destination is our control working, not their server
    breaking. Counting it as a failure would put the failure-rate alert
    into a state where blocking an attack looks like an outage.
    """
    before = _value("agentverse_tool_calls_total", status="error")

    async def _blocked(_: dict[str, Any]) -> str:
        raise EgressDeniedError("nope", category="loopback")

    await _run(redis, invoke=_blocked)

    assert _value("agentverse_tool_calls_total", status="error") == before


async def test_boundary_overhead_excludes_the_third_party_call(redis: Any) -> None:
    """The split the latency budget is built on.

    A slow third party must not show up as our overhead, or the "our
    code got slower" alert fires for someone else's network.
    """
    import asyncio

    overhead_before = _value("agentverse_tool_boundary_overhead_seconds_sum")
    duration_before = _value("agentverse_tool_call_duration_seconds_sum")

    async def _slow(_: dict[str, Any]) -> str:
        await asyncio.sleep(0.25)
        return "eventually"

    await _run(redis, invoke=_slow)

    overhead = _value("agentverse_tool_boundary_overhead_seconds_sum") - overhead_before
    duration = _value("agentverse_tool_call_duration_seconds_sum") - duration_before

    assert duration >= 0.25
    # Ours is the small part. Generous bound — this asserts the third
    # party's 250ms was excluded, not a performance budget.
    assert overhead < 0.1


async def test_retry_backoff_is_not_charged_to_boundary_overhead(redis: Any) -> None:
    """Backoff is a deliberate wait, not slowness.

    Counted as overhead it would put a multi-second sleep into a
    histogram whose p95 budget is 25ms, and the resulting page would say
    "our code got slower" while being false every time.
    """
    overhead_before = _value("agentverse_tool_boundary_overhead_seconds_sum")
    attempts = 0

    async def _flaky(_: dict[str, Any]) -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("transient")
        return "worked on the third try"

    outcome = await _run(
        redis,
        grant=ToolGrant(installed_server_id="srv-flaky", level="read_write", max_retries=2),
        invoke=_flaky,
    )

    assert outcome.status == "success"
    overhead = _value("agentverse_tool_boundary_overhead_seconds_sum") - overhead_before
    # Two backoffs of 0.5s + 1.0s elapsed; none of it is ours.
    assert overhead < 0.1


async def test_a_circuit_breaker_opening_is_counted_once_not_per_failure(redis: Any) -> None:
    """One dead server should look like one event.

    Counting every failure past the threshold would make a single
    unreachable MCP server read as a fleet-wide incident.
    """
    before = _value("agentverse_circuit_breaker_opened_total")
    breaker = CircuitBreaker(redis, failure_threshold=1)

    for _ in range(4):
        await breaker.record_failure(workspace_id="ws-1", server_id="srv-dead")

    assert _value("agentverse_circuit_breaker_opened_total") == before + 1
