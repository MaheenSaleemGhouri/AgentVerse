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
from agentverse_shared.embeddings.port import EmbeddingResult, EmbeddingUnavailableError
from agentverse_shared.retrieval.types import RetrievedChunk
from openai.types.responses import ResponseOutputText

from agents import Agent
from agents.items import MessageOutputItem, ToolCallItem, ToolCallOutputItem
from agents.stream_events import RunItemStreamEvent
from agentverse_worker.agents.grounding import KnowledgeBaseIdentity
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


class FakeDirectory:
    def __init__(self, identities: list[KnowledgeBaseIdentity] | None = None) -> None:
        self._identities = identities or []
        self.calls: list[dict[str, Any]] = []

    async def get_embedding_identities(
        self, *, workspace_id: str, knowledge_base_ids: list[str]
    ) -> list[KnowledgeBaseIdentity]:
        self.calls.append(
            {"workspace_id": workspace_id, "knowledge_base_ids": list(knowledge_base_ids)}
        )
        return [i for i in self._identities if i.id in set(knowledge_base_ids)]


class FakeSearch:
    """Records the kwargs it was called with, so tenancy is asserted on
    the *arguments* rather than on a filtered result the fake produced.
    """

    def __init__(self, chunks: list[RetrievedChunk] | None = None) -> None:
        self._chunks = chunks or []
        self.calls: list[dict[str, Any]] = []

    async def vector_search(self, **kwargs: Any) -> list[RetrievedChunk]:
        self.calls.append({"arm": "vector", **kwargs})
        return list(self._chunks)

    async def keyword_search(self, **kwargs: Any) -> list[RetrievedChunk]:
        self.calls.append({"arm": "keyword", **kwargs})
        return list(self._chunks)


class FakeEmbedder:
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if self._error is not None:
            raise self._error
        return EmbeddingResult(
            vectors=[[0.1, 0.2, 0.3] for _ in texts],
            model="text-embedding-3-small",
            model_version="1",
            prompt_tokens=len(texts),
        )

    @property
    def model(self) -> str:
        return "text-embedding-3-small"

    @property
    def model_version(self) -> str:
        return "1"


class WordCounter:
    """One token per whitespace-separated word — deterministic, so budget
    assertions are exact rather than BPE-dependent.
    """

    def count(self, text: str) -> int:
        return len(text.split())


def _chunk(chunk_id: str, content: str, *, kb_id: str = "kb-1") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        kb_document_id="doc-1",
        knowledge_base_id=kb_id,
        workspace_id=WORKSPACE_ID,
        chunk_index=0,
        content=content,
        token_count=len(content.split()),
        score=0.9,
    )


def _deps(
    *,
    directory: FakeDirectory | None = None,
    search: FakeSearch | None = None,
    embedder: FakeEmbedder | None = None,
) -> dict[str, Any]:
    """Default collaborators for tests that are not about grounding: an
    empty directory means every run is ungrounded, which is exactly the
    pre-Phase-5 behaviour those tests assert.
    """
    return {
        "directory": directory or FakeDirectory(),
        "search": search or FakeSearch(),
        "embedder": embedder or FakeEmbedder(),
        "counter": WordCounter(),
    }


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
        job,
        settings=Settings(database_url="x", openai_api_key="x"),
        redis=FakeRedis(),
        repo=repo,
        **_deps(),
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
    result = await handle_agent_run_job(job, settings=settings, redis=redis, repo=repo, **_deps())

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
    result = await handle_agent_run_job(job, settings=settings, redis=redis, repo=repo, **_deps())

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
    result = await handle_agent_run_job(job, settings=settings, redis=redis, repo=repo, **_deps())

    assert result.output == {"run_id": RUN_ID, "status": "error"}
    assert fake_result.cancelled is True
    assert "time budget" in repo.statuses[-1]["error_message"]


def _grounded_version(kb_ids: list[str]) -> VersionRecord:
    return VersionRecord(
        id=VERSION_ID,
        agent_id=AGENT_ID,
        config={
            "model": "gpt-4o-mini",
            "system_instructions": "be helpful",
            "tools": [],
            "knowledge_base_ids": kb_ids,
        },
    )


def _identity(kb_id: str, *, model: str = "text-embedding-3-small", version: str = "1"):
    return KnowledgeBaseIdentity(id=kb_id, embedding_model=model, embedding_model_version=version)


async def test_agent_without_knowledge_bases_emits_no_retrieval_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, version = _make_run_and_version()
    repo = FakeRepo(run=run, version=version)
    search = FakeSearch()
    monkeypatch.setattr(
        agent_run_job.Runner,
        "run_streamed",
        lambda *a, **k: _FakeRunResultStreaming(events=[_message_event("hi")]),
    )

    job = Job(
        job_id="j1", job_type="agent_run", payload={"run_id": RUN_ID}, attempt=0, max_attempts=3
    )
    await handle_agent_run_job(
        job,
        settings=Settings(database_url="x", openai_api_key="x"),
        redis=FakeRedis(),
        repo=repo,
        **_deps(search=search),
    )

    assert "retrieval" not in [s["step_type"] for s in repo.steps]
    # Not merely "no step" — retrieval must not have been attempted at
    # all, so an agent with no KBs never pays for an embedding call.
    assert search.calls == []


async def test_grounded_run_injects_delimited_context_and_records_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, _ = _make_run_and_version()
    repo = FakeRepo(run=run, version=_grounded_version(["kb-1"]))
    directory = FakeDirectory([_identity("kb-1")])
    search = FakeSearch([_chunk("chunk-1", "invoices are billed monthly in arrears")])

    captured: dict[str, Any] = {}

    def _capture(agent, prompt, **kwargs):
        captured["instructions"] = agent.instructions
        captured["prompt"] = prompt
        return _FakeRunResultStreaming(events=[_message_event("monthly")])

    monkeypatch.setattr(agent_run_job.Runner, "run_streamed", _capture)

    job = Job(
        job_id="j1", job_type="agent_run", payload={"run_id": RUN_ID}, attempt=0, max_attempts=3
    )
    result = await handle_agent_run_job(
        job,
        settings=Settings(database_url="x", openai_api_key="x"),
        redis=FakeRedis(),
        repo=repo,
        **_deps(directory=directory, search=search),
    )

    assert result.output == {"run_id": RUN_ID, "status": "success"}
    instructions = captured["instructions"]
    assert instructions.startswith("be helpful")
    # The system prompt survives intact and the retrieved text is fenced
    # off from it — untrusted content must be visibly data (Rule 6).
    assert "<retrieved_context>" in instructions
    assert "</retrieved_context>" in instructions
    assert "invoices are billed monthly in arrears" in instructions
    # The user prompt is unchanged; grounding rides on instructions only.
    assert captured["prompt"] == "hello"

    retrieval_steps = [s for s in repo.steps if s["step_type"] == "retrieval"]
    assert len(retrieval_steps) == 1
    payload = retrieval_steps[0]["payload"]
    assert [c["chunk_id"] for c in payload["citations"]] == ["chunk-1"]
    assert payload["error"] is None
    # The retrieval step precedes any llm_call step — the trace reads in
    # the order things actually happened.
    step_types = [s["step_type"] for s in repo.steps]
    assert step_types.index("retrieval") < step_types.index("llm_call")


async def test_retrieval_is_scoped_to_the_runs_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, _ = _make_run_and_version()
    repo = FakeRepo(run=run, version=_grounded_version(["kb-1"]))
    directory = FakeDirectory([_identity("kb-1")])
    search = FakeSearch([_chunk("chunk-1", "scoped content")])
    monkeypatch.setattr(
        agent_run_job.Runner,
        "run_streamed",
        lambda *a, **k: _FakeRunResultStreaming(events=[_message_event("ok")]),
    )

    job = Job(
        job_id="j1", job_type="agent_run", payload={"run_id": RUN_ID}, attempt=0, max_attempts=3
    )
    await handle_agent_run_job(
        job,
        settings=Settings(database_url="x", openai_api_key="x"),
        redis=FakeRedis(),
        repo=repo,
        **_deps(directory=directory, search=search),
    )

    # Asserted on the arguments both collaborators received, not on the
    # rows they returned: a search that forgot the filter would still
    # look correct against a fake that filters for it (Rule 11).
    assert directory.calls[0]["workspace_id"] == WORKSPACE_ID
    assert search.calls, "retrieval never reached the search port"
    for call in search.calls:
        assert call["workspace_id"] == WORKSPACE_ID
        assert call["knowledge_base_ids"] == ["kb-1"]


async def test_embedding_failure_degrades_the_run_instead_of_failing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, _ = _make_run_and_version()
    repo = FakeRepo(run=run, version=_grounded_version(["kb-1"]))
    directory = FakeDirectory([_identity("kb-1")])
    embedder = FakeEmbedder(error=EmbeddingUnavailableError("provider down"))

    captured: dict[str, Any] = {}

    def _capture(agent, prompt, **kwargs):
        captured["instructions"] = agent.instructions
        return _FakeRunResultStreaming(events=[_message_event("answered anyway")])

    monkeypatch.setattr(agent_run_job.Runner, "run_streamed", _capture)

    job = Job(
        job_id="j1", job_type="agent_run", payload={"run_id": RUN_ID}, attempt=0, max_attempts=3
    )
    result = await handle_agent_run_job(
        job,
        settings=Settings(database_url="x", openai_api_key="x"),
        redis=FakeRedis(),
        repo=repo,
        **_deps(directory=directory, embedder=embedder),
    )

    # Degraded, not broken: the run still succeeds ungrounded...
    assert result.output == {"run_id": RUN_ID, "status": "success"}
    assert captured["instructions"] == "be helpful"
    # ...but the failure is on the trace, not swallowed.
    retrieval_step = next(s for s in repo.steps if s["step_type"] == "retrieval")
    assert "provider down" in retrieval_step["payload"]["error"]
    assert retrieval_step["payload"]["citations"] == []


async def test_knowledge_bases_with_mismatched_embedding_identity_are_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, _ = _make_run_and_version()
    repo = FakeRepo(run=run, version=_grounded_version(["kb-1", "kb-2"]))
    directory = FakeDirectory(
        [_identity("kb-1"), _identity("kb-2", model="text-embedding-3-large")]
    )
    search = FakeSearch([_chunk("chunk-1", "matching model content")])
    monkeypatch.setattr(
        agent_run_job.Runner,
        "run_streamed",
        lambda *a, **k: _FakeRunResultStreaming(events=[_message_event("ok")]),
    )

    job = Job(
        job_id="j1", job_type="agent_run", payload={"run_id": RUN_ID}, attempt=0, max_attempts=3
    )
    await handle_agent_run_job(
        job,
        settings=Settings(database_url="x", openai_api_key="x"),
        redis=FakeRedis(),
        repo=repo,
        **_deps(directory=directory, search=search),
    )

    # Mixing embedding versions in one similarity search degrades scores
    # silently, so the mismatched KB is excluded — and named, so the user
    # can see why their documents were ignored.
    for call in search.calls:
        assert call["knowledge_base_ids"] == ["kb-1"]
    retrieval_step = next(s for s in repo.steps if s["step_type"] == "retrieval")
    assert retrieval_step["payload"]["skipped_knowledge_base_ids"] == ["kb-2"]
