"""Concurrency measurement for the tool-execution boundary.

`CLAUDE.md` §17 requires a measured actual against a published budget,
and §19 item 6 will not pass on a budget alone. This measures the one
number in `docs/performance/tool-execution-budgets.md` that is actually
ours: **boundary overhead**, which excludes the third party's call and
the retry backoff.

Measuring end-to-end latency instead would measure a stub, which is
worthless. Measuring our own overhead under concurrency against a real
Redis is not — the breaker, budget, and cache each make Redis round
trips, and whether those hold up when many tool calls run at once is a
genuine question the unit tests do not answer.

Marked `integration` and skipped without a real Redis, never silently
passed against a fake: `fakeredis` is in-process and would report
latency that has nothing to do with a deployed system.
"""

from __future__ import annotations

import asyncio
import os
import statistics
import time
import uuid
from typing import Any

import pytest
from redis.asyncio import Redis

from agentverse_worker.tools.boundary import (
    ExecutionContext,
    ToolDefinition,
    ToolGrant,
    execute_tool,
)
from agentverse_worker.tools.policy import (
    DEFAULT_FAILURE_THRESHOLD,
    CallBudget,
    CircuitBreaker,
    ResultCache,
)

pytestmark = pytest.mark.integration

_REDIS_URL = os.environ.get("AGENTVERSE_WORKER_REDIS_URL")

#: Budget from docs/performance/tool-execution-budgets.md, in absolute
#: terms. Reported, never asserted — see below.
BUDGET_P95_SECONDS = 0.025

#: What is actually asserted: boundary overhead measured in *Redis round
#: trips*, not milliseconds.
#:
#: The first version of this test asserted absolute time and failed at
#: p95=208ms against a 25ms budget. Investigating rather than loosening
#: the number showed the boundary was not at fault: the same concurrency
#: against a bare `PING` costs nearly as much, because the developer
#: Redis here is a container reached across a WSL↔Windows port forward.
#: An absolute assertion measures whoever's laptop runs it.
#:
#: A permitted call makes a bounded number of Redis calls — breaker state
#: (2), budget consume (1–2), breaker success (1) — so overhead should be
#: a small multiple of one round trip on any host. That ratio is the
#: property of *our code*, and it is what regresses if someone adds a
#: gratuitous round trip to the hot path. §17: name the dominant
#: contributor rather than optimising the wrong layer.
MAX_OVERHEAD_IN_ROUND_TRIPS = 12

#: Enough concurrency to contend for Redis connections without turning
#: the suite into a load generator that slows every other test.
CONCURRENCY = 50
CALLS_PER_TASK = 20

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"repo": {"type": "string"}},
    "required": ["repo"],
    "additionalProperties": False,
}
TOOL = ToolDefinition(
    name="list_issues", description="Lists issues.", input_schema=SCHEMA, is_mutating=False
)


class NullRecorder:
    """Records nothing.

    The `tool_calls` write is a Postgres round trip that belongs to the
    database budget, not this one. Including it would mean reporting a
    number that answers a different question than the one the budget
    asks.
    """

    async def record_call(self, **kwargs: Any) -> None:
        return None


@pytest.fixture
async def redis() -> Any:
    if not _REDIS_URL:
        pytest.skip("AGENTVERSE_WORKER_REDIS_URL not set — load measurement needs a real Redis")
    client = Redis.from_url(_REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:  # noqa: BLE001 - unreachable Redis is a skip, not a failure
        await client.aclose()
        pytest.skip(f"no Redis reachable at {_REDIS_URL}")
    yield client
    await client.aclose()


async def _redis_round_trip_p95(redis: Any) -> float:
    """Cost of one trivial Redis command at the same concurrency.

    The baseline that makes the boundary number interpretable. Without
    it, "overhead p95 is 208ms" cannot distinguish slow code from a slow
    network, and the obvious next move — optimising the boundary — would
    be wasted effort.
    """
    samples: list[float] = []

    async def _task() -> None:
        for _ in range(CALLS_PER_TASK):
            started = time.monotonic()
            await redis.ping()
            samples.append(time.monotonic() - started)

    await asyncio.gather(*(_task() for _ in range(CONCURRENCY)))
    return sorted(samples)[int(len(samples) * 0.95)]


async def test_boundary_overhead_under_concurrency(redis: Any) -> None:
    """1000 governed calls across 50 concurrent tasks."""
    baseline_p95 = await _redis_round_trip_p95(redis)
    breaker = CircuitBreaker(redis)
    cache = ResultCache(redis)
    budget = CallBudget(redis)
    recorder = NullRecorder()
    overheads: list[float] = []

    async def _invoke(_: dict[str, Any]) -> str:
        # A trivial coroutine standing in for the third party. Its cost
        # is measured and subtracted by the boundary itself, so what
        # lands in `overheads` is ours.
        return "three issues found"

    # Unique per execution. The per-run budget counter lives in Redis
    # with a one-hour TTL, so fixed ids would make a second run inside
    # that hour exhaust a budget the first run already spent — the test
    # would pass alone and fail in a suite, which is the worst kind of
    # failure to debug.
    run_tag = uuid.uuid4().hex[:8]

    async def _task(task_id: int) -> None:
        grant = ToolGrant(
            installed_server_id=f"srv-{run_tag}-{task_id}",
            level="read_write",
            max_calls_per_run=CALLS_PER_TASK * 2,
        )
        context = ExecutionContext(
            workspace_id=f"ws-{run_tag}-{task_id}", run_id=f"run-{run_tag}-{task_id}"
        )
        for _ in range(CALLS_PER_TASK):
            started = time.monotonic()
            outcome = await execute_tool(
                tool=TOOL,
                arguments={"repo": "agentverse"},
                grant=grant,
                context=context,
                invoke=_invoke,
                recorder=recorder,
                breaker=breaker,
                cache=cache,
                budget=budget,
            )
            assert outcome.status == "success", outcome.denial_reason or outcome.error_message
            overheads.append(time.monotonic() - started)

    await asyncio.gather(*(_task(i) for i in range(CONCURRENCY)))

    ordered = sorted(overheads)
    p50 = statistics.median(ordered)
    p95 = ordered[int(len(ordered) * 0.95)]
    p99 = ordered[int(len(ordered) * 0.99)]

    in_round_trips = p95 / baseline_p95 if baseline_p95 > 0 else float("inf")

    rtt_needed = BUDGET_P95_SECONDS / MAX_OVERHEAD_IN_ROUND_TRIPS * 1000
    print(
        f"\nboundary overhead over {len(ordered)} calls at concurrency {CONCURRENCY}:"
        f"\n  p50={p50 * 1000:.2f}ms p95={p95 * 1000:.2f}ms p99={p99 * 1000:.2f}ms"
        f"\n  redis round-trip p95={baseline_p95 * 1000:.2f}ms on this host"
        f"\n  overhead = {in_round_trips:.1f} round trips"
        f"\n  absolute budget p95 {BUDGET_P95_SECONDS * 1000:.0f}ms is met where a"
        f" round trip costs under {rtt_needed:.1f}ms"
    )

    assert len(ordered) == CONCURRENCY * CALLS_PER_TASK
    assert in_round_trips < MAX_OVERHEAD_IN_ROUND_TRIPS, (
        f"boundary overhead p95 is {in_round_trips:.1f} Redis round trips "
        f"({p95 * 1000:.2f}ms against a {baseline_p95 * 1000:.2f}ms baseline) — the hot path "
        f"has gained round trips, which is a code regression rather than a slow host"
    )


async def test_a_refusal_is_cheaper_than_a_permitted_call(redis: Any) -> None:
    """Refusals must stay cheap, and this is the claim the budget doc
    makes without evidence.

    It matters because a refusal is the path an attacker exercises
    repeatedly: an injected instruction can fire hundreds of denied
    calls, and if each cost as much as a real one the permission check
    would be an amplifier rather than a control. The boundary orders its
    checks cheapest-first specifically so this holds — this measures
    whether the ordering actually delivers it.
    """
    breaker = CircuitBreaker(redis)
    cache = ResultCache(redis)
    budget = CallBudget(redis)
    recorder = NullRecorder()

    mutating = ToolDefinition(
        name="delete_repo", description="Deletes.", input_schema=SCHEMA, is_mutating=True
    )

    async def _invoke(_: dict[str, Any]) -> str:
        return "should never run"

    async def _measure(tool: ToolDefinition, level: str, expected: str) -> float:
        grant = ToolGrant(installed_server_id="srv-refusal", level=level, max_calls_per_run=10_000)
        context = ExecutionContext(workspace_id="ws-refusal", run_id="run-refusal")
        samples: list[float] = []
        for _ in range(200):
            started = time.monotonic()
            outcome = await execute_tool(
                tool=tool,
                arguments={"repo": "agentverse"},
                grant=grant,
                context=context,
                invoke=_invoke,
                recorder=recorder,
                breaker=breaker,
                cache=cache,
                budget=budget,
            )
            assert outcome.status == expected
            samples.append(time.monotonic() - started)
        return statistics.median(samples)

    permitted = await _measure(TOOL, "read_write", "success")
    refused = await _measure(mutating, "read_only", "denied")

    print(
        f"\nmedian permitted={permitted * 1000:.2f}ms refused={refused * 1000:.2f}ms "
        f"({refused / permitted:.2f}x)"
    )

    # A refusal short-circuits before the budget, cache, and network, so
    # it must not cost more than a call that does all of them.
    assert refused <= permitted, (
        f"a refused call ({refused * 1000:.2f}ms) cost more than a permitted one "
        f"({permitted * 1000:.2f}ms) — the cheapest-first check ordering has regressed"
    )


class TestCircuitBreakerConcurrency:
    """`policy.py`'s own module docstring is the claim under test here:
    a per-process breaker would let a fleet hammer a dying server eight
    times over before each replica's copy independently opened. The
    Redis-backed breaker is supposed to fix that — but every existing
    test (`test_boundary.py::TestCircuitBreaker`) drives failures one at
    a time, which cannot show whether the `SET ... GET` transition that
    opens the breaker stays correct when many failures race it at once,
    or whether an already-open breaker actually stops a concurrent wave
    rather than merely reducing it.
    """

    async def test_a_wave_after_opening_is_fully_blocked_and_opens_exactly_once(
        self, redis: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import agentverse_worker.tools.policy as policy_module

        opened_count = 0

        def _count_opened() -> None:
            nonlocal opened_count
            opened_count += 1

        monkeypatch.setattr(policy_module, "record_breaker_opened", _count_opened)

        breaker = CircuitBreaker(redis)
        cache = ResultCache(redis)
        budget = CallBudget(redis)
        recorder = NullRecorder()
        run_tag = uuid.uuid4().hex[:8]
        # `max_retries=0` so each `execute_tool` call records exactly one
        # failure — otherwise a single call's own internal retries would
        # be indistinguishable from separate concurrent callers racing.
        grant = ToolGrant(
            installed_server_id=f"srv-dead-{run_tag}", level="read_write", max_retries=0
        )
        context = ExecutionContext(workspace_id=f"ws-dead-{run_tag}", run_id=f"run-dead-{run_tag}")

        invoke_calls = 0

        async def _dying_invoke(_: dict[str, Any]) -> str:
            nonlocal invoke_calls
            invoke_calls += 1
            raise RuntimeError("server is down")

        async def _call() -> Any:
            return await execute_tool(
                tool=TOOL,
                arguments={"repo": "agentverse"},
                grant=grant,
                context=context,
                invoke=_dying_invoke,
                recorder=recorder,
                breaker=breaker,
                cache=cache,
                budget=budget,
            )

        # Wave 1: 20 concurrent failures against the same server, all
        # racing the same threshold crossing at once — the scenario a
        # sequential unit test cannot produce.
        first_wave = await asyncio.gather(*(_call() for _ in range(20)))
        assert all(outcome.status == "error" for outcome in first_wave)

        state = await breaker.state(
            workspace_id=context.workspace_id, server_id=grant.installed_server_id
        )
        assert state.is_open

        # However many of the 20 raced past the closed-breaker check
        # before it opened, the open transition itself must have fired
        # exactly once — a race in the `SET ... get=True` pattern would
        # show up here as more than one.
        assert opened_count == 1

        invoke_calls_after_first_wave = invoke_calls
        assert invoke_calls_after_first_wave >= DEFAULT_FAILURE_THRESHOLD

        # Wave 2, fired only once the breaker is confirmed open: this is
        # the guarantee that actually matters — a dying server sees zero
        # further calls from a wave that arrives after the breaker has
        # opened, not just fewer of them.
        second_wave = await asyncio.gather(*(_call() for _ in range(20)))
        assert all(outcome.status == "circuit_open" for outcome in second_wave)
        assert invoke_calls == invoke_calls_after_first_wave, (
            "the open breaker let a call through to the dead server after opening"
        )
