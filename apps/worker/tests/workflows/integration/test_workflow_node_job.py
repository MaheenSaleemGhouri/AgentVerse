"""End-to-end DAG execution against real Postgres + real Redis, with
only the OpenAI Agents SDK's `Runner.run_streamed` monkeypatched
(mirrors `tests/agents/test_agent_run_job.py`'s approach) — everything
else, including the in-process delegation to `handle_agent_run_job`,
runs for real. This is the guarantee a fake repository cannot prove:
that a `workflow_node` job actually creates a real `agent_runs` row,
executes it via the real function, and durably pauses at a
`human_approval` node without losing state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from openai.types.responses import ResponseOutputText
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents import Agent
from agents.items import MessageOutputItem
from agents.stream_events import RunItemStreamEvent
from agentverse_worker.agents.grounding import KnowledgeBaseIdentity
from agentverse_worker.agents.repository import WorkerAgentRepository
from agentverse_worker.infrastructure.config import Settings
from agentverse_worker.jobs import agent_run_job
from agentverse_worker.jobs.workflow_node_job import WorkflowExecutionDeps, handle_workflow_node_job
from agentverse_worker.queue.models import Job
from agentverse_worker.teams.repository import WorkerTeamRepository
from agentverse_worker.workflows.repository import WorkerWorkflowRepository

_FAKE_AGENT = Agent(name="test-agent", instructions="be helpful")


@dataclass
class _FakeUsage:
    input_tokens: int = 10
    output_tokens: int = 5


@dataclass
class _FakeContextWrapper:
    usage: _FakeUsage = field(default_factory=_FakeUsage)


class _FakeRunResultStreaming:
    def __init__(self, text: str) -> None:
        raw = SimpleNamespace(
            content=[ResponseOutputText(text=text, type="output_text", annotations=[])]
        )
        item = MessageOutputItem(agent=_FAKE_AGENT, raw_item=raw)
        self._events = [RunItemStreamEvent(name="message_output_created", item=item)]
        self.context_wrapper = _FakeContextWrapper()

    async def stream_events(self):
        for event in self._events:
            yield event

    def cancel(self) -> None:
        pass


class _EmptyDirectory:
    async def get_embedding_identities(
        self, *, workspace_id: str, knowledge_base_ids: list[str]
    ) -> list[KnowledgeBaseIdentity]:
        return []


class _EmptySearch:
    async def vector_search(self, **kwargs: object) -> list[object]:
        return []

    async def keyword_search(self, **kwargs: object) -> list[object]:
        return []


class _NullEmbedder:
    @property
    def model(self) -> str:
        return "text-embedding-3-small"

    @property
    def model_version(self) -> str:
        return "1"


class _WordCounter:
    def count(self, text: str) -> int:
        return len(text.split())


async def _deps(
    session: AsyncSession, *, redis: Redis, session_factory: async_sessionmaker[AsyncSession]
) -> WorkflowExecutionDeps:
    return WorkflowExecutionDeps(
        settings=Settings(database_url="x", openai_api_key="x"),
        redis=redis,
        queue_stream="queue:jobs:test",
        workflow_repo=WorkerWorkflowRepository(session),
        agent_repo=WorkerAgentRepository(session),
        team_repo=WorkerTeamRepository(session),
        directory=_EmptyDirectory(),  # type: ignore[arg-type]
        search=_EmptySearch(),  # type: ignore[arg-type]
        embedder=_NullEmbedder(),  # type: ignore[arg-type]
        counter=_WordCounter(),
        integrations=None,
        session_factory=session_factory,
    )


async def test_agent_step_executes_for_real_and_pauses_at_the_approval_node(
    monkeypatch: pytest.MonkeyPatch,
    workflow_fixture: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    monkeypatch.setattr(
        agent_run_job.Runner,
        "run_streamed",
        lambda *a, **k: _FakeRunResultStreaming("category: billing"),
    )
    redis: Redis = Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    stream = f"queue:jobs:test:pause:{uuid.uuid4().hex[:8]}"

    async with session_factory() as session:
        deps = await _deps(session, redis=redis, session_factory=session_factory)
        deps.queue_stream = stream
        job = Job(
            job_id="j1",
            job_type="workflow_node",
            payload={
                "workflow_run_id": workflow_fixture["run_id"],
                "node_id": workflow_fixture["node1_id"],
            },
            attempt=0,
            max_attempts=1,
        )
        result = await handle_workflow_node_job(job, deps=deps)
        await session.commit()

    assert result.output is not None
    assert result.output["status"] == "success"

    async with session_factory() as session:
        wf_repo = WorkerWorkflowRepository(session)
        node1_run = await wf_repo.get_node_run(
            workflow_run_id=workflow_fixture["run_id"], node_id=workflow_fixture["node1_id"]
        )
        assert node1_run is not None
        assert node1_run.status == "success"
        assert node1_run.output == {"text": "category: billing"}
        assert node1_run.agent_run_id is not None

        agent_run_count = await session.execute(
            text("SELECT count(*) FROM agent_runs WHERE agent_id = :agent"),
            {"agent": workflow_fixture["agent_id"]},
        )
        assert agent_run_count.scalar_one() == 1

    # node1's completion *enqueued* node2's job — it does not execute it
    # inline (that would defeat the point of a queue). One job is now
    # waiting on the stream, exactly as a real worker's next poll would
    # find it.
    assert await redis.xlen(stream) == 1

    async with session_factory() as session:
        deps = await _deps(session, redis=redis, session_factory=session_factory)
        deps.queue_stream = stream
        node2_job = Job(
            job_id="j2",
            job_type="workflow_node",
            payload={
                "workflow_run_id": workflow_fixture["run_id"],
                "node_id": workflow_fixture["node2_id"],
            },
            attempt=0,
            max_attempts=1,
        )
        await handle_workflow_node_job(node2_job, deps=deps)
        await session.commit()

    async with session_factory() as session:
        wf_repo = WorkerWorkflowRepository(session)
        run = await wf_repo.get_run(workflow_fixture["run_id"])
        assert run is not None
        assert run.status == "paused"

        node2_run = await wf_repo.get_node_run(
            workflow_run_id=workflow_fixture["run_id"], node_id=workflow_fixture["node2_id"]
        )
        assert node2_run is not None
        assert node2_run.status == "paused_for_approval"

    # A human_approval node stops there — it never itself enqueues
    # further (the `/resolve` route is what drives it forward).
    assert await redis.xlen(stream) == 1  # still just node2's own consumed entry, untouched

    await redis.aclose()


async def test_redelivered_job_does_not_re_execute_a_terminal_node(
    monkeypatch: pytest.MonkeyPatch,
    workflow_fixture: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    calls = {"n": 0}

    def _run_streamed(*a: object, **k: object) -> _FakeRunResultStreaming:
        calls["n"] += 1
        return _FakeRunResultStreaming("first and only run")

    monkeypatch.setattr(agent_run_job.Runner, "run_streamed", _run_streamed)
    redis: Redis = Redis.from_url("redis://localhost:6379/0", decode_responses=True)

    job = Job(
        job_id="j1",
        job_type="workflow_node",
        payload={
                "workflow_run_id": workflow_fixture["run_id"],
                "node_id": workflow_fixture["node1_id"],
            },
        attempt=0,
        max_attempts=1,
    )

    async with session_factory() as session:
        deps = await _deps(session, redis=redis, session_factory=session_factory)
        await handle_workflow_node_job(job, deps=deps)
        await session.commit()

    # Redelivery: the exact same job arrives again (at-least-once queue).
    async with session_factory() as session:
        deps = await _deps(session, redis=redis, session_factory=session_factory)
        await handle_workflow_node_job(job, deps=deps)
        await session.commit()

    assert calls["n"] == 1  # the SDK was never invoked a second time

    async with session_factory() as session:
        agent_run_count = await session.execute(
            text("SELECT count(*) FROM agent_runs WHERE agent_id = :agent"),
            {"agent": workflow_fixture["agent_id"]},
        )
        assert agent_run_count.scalar_one() == 1

    await redis.aclose()
