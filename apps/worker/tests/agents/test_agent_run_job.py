"""Exercises the executor's own logic — bounds enforcement, status
transitions, step recording — with the OpenAI Agents SDK's
`Runner.run_streamed` monkeypatched to a controlled fake. Real SDK
event/item dataclasses are constructed directly (not duck-typed stand-
ins) so the `isinstance` checks in `agent_run_job.py` are exercised
against the actual types they'll see in production.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from openai.types.responses import ResponseOutputText

from agents import Agent
from agents.items import MessageOutputItem, ToolCallItem, ToolCallOutputItem
from agents.stream_events import RunItemStreamEvent
from agentverse_worker.agents.repository import RunRecord, VersionRecord
from agentverse_worker.infrastructure.config import Settings
from agentverse_worker.jobs import agent_run_job
from agentverse_worker.jobs.agent_run_job import handle_agent_run_job
from agentverse_worker.queue.models import Job

WORKSPACE_ID = "ws-1"
RUN_ID = "run-1"
AGENT_ID = "agent-1"
VERSION_ID = "version-1"

_FAKE_AGENT = Agent(name="test-agent", instructions="be helpful")


def _message_event(text: str) -> RunItemStreamEvent:
    raw = SimpleNamespace(
        content=[ResponseOutputText(text=text, type="output_text", annotations=[])]
    )
    item = MessageOutputItem(agent=_FAKE_AGENT, raw_item=raw)
    return RunItemStreamEvent(name="message_output_created", item=item)


def _tool_called_event(name: str, arguments: str) -> RunItemStreamEvent:
    raw = SimpleNamespace(name=name, arguments=arguments)
    item = ToolCallItem(agent=_FAKE_AGENT, raw_item=raw)
    return RunItemStreamEvent(name="tool_called", item=item)


def _tool_output_event(output: str) -> RunItemStreamEvent:
    item = ToolCallOutputItem(agent=_FAKE_AGENT, raw_item=SimpleNamespace(), output=output)
    return RunItemStreamEvent(name="tool_output", item=item)


@dataclass
class _FakeUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class _FakeContextWrapper:
    usage: _FakeUsage = field(default_factory=_FakeUsage)


class _FakeRunResultStreaming:
    def __init__(self, events: list[RunItemStreamEvent], *, final_usage: _FakeUsage | None = None):
        self._events = events
        self.context_wrapper = _FakeContextWrapper()
        self._final_usage = final_usage or _FakeUsage(input_tokens=10, output_tokens=5)
        self.cancelled = False

    async def stream_events(self):
        for event in self._events:
            yield event
        self.context_wrapper.usage = self._final_usage

    def cancel(self) -> None:
        self.cancelled = True


@dataclass
class FakeRepo:
    run: RunRecord
    version: VersionRecord
    statuses: list[dict[str, Any]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)

    async def get_run(self, run_id: str) -> RunRecord | None:
        return self.run if run_id == self.run.id else None

    async def get_version(self, version_id: str) -> VersionRecord | None:
        return self.version if version_id == self.version.id else None

    async def update_run_status(
        self, *, run_id: str, status: str, cost_micro_usd: int | None = None, error_message=None
    ) -> None:
        self.statuses.append(
            {"status": status, "cost_micro_usd": cost_micro_usd, "error_message": error_message}
        )

    async def append_step(
        self, *, step_id, run_id, workspace_id, step_type, sequence, payload, cost_micro_usd
    ) -> None:
        self.steps.append({"step_type": step_type, "sequence": sequence, "payload": payload})


class FakeRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> None:
        self.published.append((channel, message))


def _make_run_and_version() -> tuple[RunRecord, VersionRecord]:
    run = RunRecord(
        id=RUN_ID,
        workspace_id=WORKSPACE_ID,
        agent_id=AGENT_ID,
        agent_version_id=VERSION_ID,
        status="queued",
        input={"prompt": "hello"},
    )
    version = VersionRecord(
        id=VERSION_ID,
        agent_id=AGENT_ID,
        config={"model": "gpt-4o-mini", "system_instructions": "be helpful", "tools": []},
    )
    return run, version


async def test_missing_run_fails_without_touching_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    run, version = _make_run_and_version()
    repo = FakeRepo(run=run, version=version)

    def _should_not_be_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("Runner.run_streamed must not be called for a missing run")

    monkeypatch.setattr(agent_run_job.Runner, "run_streamed", _should_not_be_called)

    job = Job(
        job_id="j1",
        job_type="agent_run",
        payload={"run_id": "does-not-exist"},
        attempt=0,
        max_attempts=3,
    )
    result = await handle_agent_run_job(
        job, settings=Settings(database_url="x", openai_api_key="x"), redis=FakeRedis(), repo=repo
    )

    assert result.error is not None
    assert repo.statuses == []


async def test_successful_run_records_steps_and_success_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, version = _make_run_and_version()
    repo = FakeRepo(run=run, version=version)
    redis = FakeRedis()

    fake_result = _FakeRunResultStreaming(
        events=[
            _message_event("Hello there"),
            _tool_called_event("calculator", '{"expression": "2 + 2"}'),
            _tool_output_event("4.0"),
        ],
        final_usage=_FakeUsage(input_tokens=20, output_tokens=10),
    )
    monkeypatch.setattr(agent_run_job.Runner, "run_streamed", lambda *a, **k: fake_result)

    job = Job(
        job_id="j1", job_type="agent_run", payload={"run_id": RUN_ID}, attempt=0, max_attempts=3
    )
    settings = Settings(database_url="x", openai_api_key="x")
    result = await handle_agent_run_job(job, settings=settings, redis=redis, repo=repo)

    assert result.output == {"run_id": RUN_ID, "status": "success"}
    statuses = [s["status"] for s in repo.statuses]
    assert statuses == ["running", "success"]
    assert (
        repo.statuses[-1]["cost_micro_usd"] is not None and repo.statuses[-1]["cost_micro_usd"] > 0
    )

    step_types = [s["step_type"] for s in repo.steps]
    assert step_types == ["run_started", "llm_call", "tool_call", "tool_call", "run_completed"]
    tool_call_steps = [s for s in repo.steps if s["step_type"] == "tool_call"]
    assert tool_call_steps[0]["payload"]["phase"] == "called"
    assert tool_call_steps[0]["payload"]["name"] == "calculator"
    assert tool_call_steps[1]["payload"]["phase"] == "output"
    assert tool_call_steps[1]["payload"]["output"] == "4.0"

    published_types = [json.loads(msg)["type"] for _ch, msg in redis.published]
    assert published_types == ["run_started", "llm_call", "tool_call", "tool_call", "run_completed"]
    # Live-published events now carry the same shape as persisted steps
    # (sequence/payload/cost) — a reconnecting client backfilling from
    # agent_run_steps and a live subscriber see identical event shapes.
    published_payloads = [json.loads(msg) for _ch, msg in redis.published]
    llm_call_event = published_payloads[1]
    assert llm_call_event["payload"] == {"text": "Hello there"}
    assert llm_call_event["sequence"] == 2


async def test_cost_ceiling_exceeded_aborts_run(monkeypatch: pytest.MonkeyPatch) -> None:
    run, version = _make_run_and_version()
    repo = FakeRepo(run=run, version=version)
    redis = FakeRedis()

    # gpt-4o-mini pricing: even a small usage produces nonzero micro-USD
    # cost — a ceiling of 0 always trips on the first bounds check.
    fake_result = _FakeRunResultStreaming(events=[_message_event("partial")])
    fake_result.context_wrapper.usage = _FakeUsage(input_tokens=1000, output_tokens=1000)
    monkeypatch.setattr(agent_run_job.Runner, "run_streamed", lambda *a, **k: fake_result)

    job = Job(
        job_id="j1", job_type="agent_run", payload={"run_id": RUN_ID}, attempt=0, max_attempts=3
    )
    settings = Settings(database_url="x", openai_api_key="x", run_cost_ceiling_micro_usd=0)
    result = await handle_agent_run_job(job, settings=settings, redis=redis, repo=repo)

    assert result.output == {"run_id": RUN_ID, "status": "error"}
    assert fake_result.cancelled is True
    statuses = [s["status"] for s in repo.statuses]
    assert statuses == ["running", "error"]
    assert "cost ceiling" in repo.statuses[-1]["error_message"]
    assert repo.steps[-1]["step_type"] == "run_failed"


async def test_time_budget_exceeded_aborts_run(monkeypatch: pytest.MonkeyPatch) -> None:
    run, version = _make_run_and_version()
    repo = FakeRepo(run=run, version=version)
    redis = FakeRedis()

    fake_result = _FakeRunResultStreaming(events=[_message_event("partial")])
    monkeypatch.setattr(agent_run_job.Runner, "run_streamed", lambda *a, **k: fake_result)

    job = Job(
        job_id="j1", job_type="agent_run", payload={"run_id": RUN_ID}, attempt=0, max_attempts=3
    )
    # Any elapsed time exceeds a zero-second budget.
    settings = Settings(database_url="x", openai_api_key="x", run_timeout_seconds=0.0)
    result = await handle_agent_run_job(job, settings=settings, redis=redis, repo=repo)

    assert result.output == {"run_id": RUN_ID, "status": "error"}
    assert fake_result.cancelled is True
    assert "time budget" in repo.statuses[-1]["error_message"]
