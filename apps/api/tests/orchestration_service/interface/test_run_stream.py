"""Exercises `stream_run_events` directly (CLAUDE.md §11) rather than
through the full HTTP route — testing genuine concurrent pub/sub
delivery through `httpx.AsyncClient` would mean fighting ASGI streaming
timing for no extra confidence; this is the same logic either way.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from fakeredis.aioredis import FakeRedis

from agentverse_api.orchestration_service.domain.run_entities import (
    AgentRunStep,
    RunStepType,
)
from agentverse_api.orchestration_service.interface.routers.run_stream import (
    channel_name,
    stream_run_events,
)
from tests.fakes.orchestration_repositories import FakeAgentRunRepository

RUN_ID = "run-1"
WORKSPACE_ID = "ws-1"


def _step(step_type: RunStepType, sequence: int, payload: dict) -> AgentRunStep:
    return AgentRunStep(
        id=f"step-{sequence}",
        run_id=RUN_ID,
        workspace_id=WORKSPACE_ID,
        step_type=step_type,
        sequence=sequence,
        payload=payload,
        cost_micro_usd=None,
        created_at=datetime.now(UTC),
    )


async def test_backfills_persisted_steps_in_order(fake_redis: FakeRedis) -> None:
    repo = FakeAgentRunRepository()
    repo.steps[RUN_ID] = [
        _step(RunStepType.RUN_STARTED, 1, {}),
        _step(RunStepType.LLM_CALL, 2, {"text": "hi"}),
    ]

    # run_status="success": this test asserts backfill content/order
    # only — a non-terminal status with no terminal step in the backlog
    # would (correctly) make the generator open a pub/sub subscription
    # and wait for a publisher that never arrives in this test.
    frames = [
        frame
        async for frame in stream_run_events(repo, fake_redis, run_id=RUN_ID, run_status="success")
    ]

    parsed = [json.loads(f[len("data: ") :]) for f in frames]
    assert [p["type"] for p in parsed] == ["run_started", "llm_call"]
    assert parsed[1]["payload"] == {"text": "hi"}


async def test_closes_immediately_if_backfill_already_terminal(fake_redis: FakeRedis) -> None:
    repo = FakeAgentRunRepository()
    repo.steps[RUN_ID] = [
        _step(RunStepType.RUN_STARTED, 1, {}),
        _step(RunStepType.RUN_COMPLETED, 2, {"prompt_tokens": 5, "completion_tokens": 3}),
    ]

    frames = [
        frame
        async for frame in stream_run_events(repo, fake_redis, run_id=RUN_ID, run_status="success")
    ]

    # Exactly the two backfilled frames — no pub/sub subscription ever
    # opened for an already-finished run.
    assert len(frames) == 2
    assert await fake_redis.pubsub_numsub(channel_name(RUN_ID)) == [(channel_name(RUN_ID), 0)]


async def test_streams_live_events_until_terminal(fake_redis: FakeRedis) -> None:
    repo = FakeAgentRunRepository()
    repo.steps[RUN_ID] = [_step(RunStepType.RUN_STARTED, 1, {})]

    async def _publisher() -> None:
        # Give the generator a moment to subscribe before publishing —
        # a real subscriber must be attached for PUBLISH to deliver.
        for _ in range(20):
            if await fake_redis.pubsub_numsub(channel_name(RUN_ID)) != [(channel_name(RUN_ID), 0)]:
                break
            await asyncio.sleep(0.01)
        await fake_redis.publish(
            channel_name(RUN_ID), json.dumps({"type": "llm_call", "sequence": 2, "payload": {}})
        )
        await fake_redis.publish(
            channel_name(RUN_ID),
            json.dumps({"type": "run_completed", "sequence": 3, "payload": {}}),
        )

    async def _consume() -> list[dict]:
        return [
            json.loads(frame[len("data: ") :])
            async for frame in stream_run_events(
                repo, fake_redis, run_id=RUN_ID, run_status="running"
            )
        ]

    _, events = await asyncio.gather(_publisher(), _consume())

    types = [e["type"] for e in events]
    assert types == ["run_started", "llm_call", "run_completed"]


async def test_pubsub_subscription_is_released_after_terminal_event(fake_redis: FakeRedis) -> None:
    repo = FakeAgentRunRepository()
    repo.steps[RUN_ID] = []

    async def _publisher() -> None:
        for _ in range(20):
            if await fake_redis.pubsub_numsub(channel_name(RUN_ID)) != [(channel_name(RUN_ID), 0)]:
                break
            await asyncio.sleep(0.01)
        await fake_redis.publish(channel_name(RUN_ID), json.dumps({"type": "run_completed"}))

    async def _consume() -> None:
        async for _frame in stream_run_events(
            repo, fake_redis, run_id=RUN_ID, run_status="running"
        ):
            pass

    await asyncio.gather(_publisher(), _consume())

    assert await fake_redis.pubsub_numsub(channel_name(RUN_ID)) == [(channel_name(RUN_ID), 0)]
