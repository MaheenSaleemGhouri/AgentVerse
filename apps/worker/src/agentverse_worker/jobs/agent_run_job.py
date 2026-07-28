"""Executes an `agent_run` job (docs/roadmap.md Phase 4) via the OpenAI
Agents SDK's `Agent`/`Runner` — no custom orchestration loop, tool-call
dispatch, or turn management is built; the SDK owns all of that. This
module's only job is translating the SDK's own stream events into
`agent_run_steps` rows and `run:{run_id}:events` pub/sub messages, and
computing cost via the shared `cost_accounting` module from the SDK's
own reported usage.

Step granularity, not token granularity (per the Phase 4 M1 schema
design): individual token deltas are published live only, via
`agents.events.publish_event`, never persisted as their own
`agent_run_steps` row.

Bounds (CLAUDE.md Rule 17 — step, cost, AND time, not just one):
- Step: the SDK's own `max_turns` on `Runner.run_streamed` — the SDK
  already provides this, so it is used directly, not reimplemented.
- Time and cost: the SDK has no notion of AgentVerse's pricing or
  latency budget, so these are checked here, and `result.cancel()` (an
  SDK-provided method, not a custom cancellation mechanism) is called
  when either is exceeded.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agentverse_shared.cost_accounting import TokenUsage, calculate_cost_micro_usd
from agentverse_shared.embeddings.port import EmbeddingProvider
from agentverse_shared.retrieval.port import ChunkSearchPort
from agentverse_shared.text.tokenizer import TokenCounter
from redis.asyncio import Redis

from agents import Agent, ItemHelpers, ModelSettings, Runner
from agents.items import MessageOutputItem, ToolCallItem, ToolCallOutputItem
from agents.stream_events import RunItemStreamEvent
from agentverse_worker.agents.builtin_tools import resolve_tools
from agentverse_worker.agents.events import publish_event
from agentverse_worker.agents.grounding import KnowledgeBaseDirectory, ground_run
from agentverse_worker.agents.repository import (
    AgentRepositoryProtocol,
    RunRecord,
    VersionRecord,
)
from agentverse_worker.infrastructure.config import Settings
from agentverse_worker.mcp.attach import AttachmentResult, attach_integrations
from agentverse_worker.mcp.repository import IntegrationRepositoryProtocol
from agentverse_worker.queue.models import Job, JobResult
from agentverse_worker.tools.boundary import BoundaryDeps, ExecutionContext
from agentverse_worker.tools.policy import CallBudget, CircuitBreaker, ResultCache

logger = logging.getLogger(__name__)

#: Used when the agent config leaves `max_output_tokens` unset. The
#: context budget is computed by subtraction, so *something* must be
#: reserved for the response — reserving nothing would let retrieved
#: context fill the window and leave no room to answer.
_DEFAULT_RESERVED_OUTPUT_TOKENS = 2048


class _RunAbortedError(Exception):
    """Raised internally when a bound (time/cost) is exceeded — caught
    within this module only, never escapes to the queue as a retryable
    failure. Exceeding a budget is an expected outcome, not a bug to retry.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


async def handle_agent_run_job(
    job: Job,
    *,
    settings: Settings,
    redis: Redis,
    repo: AgentRepositoryProtocol,
    directory: KnowledgeBaseDirectory,
    search: ChunkSearchPort,
    embedder: EmbeddingProvider,
    counter: TokenCounter,
    #: Optional so every pre-Phase-6 caller and unit test keeps working
    #: unchanged: `None` means "this run has no MCP integrations", which
    #: is exactly the old behaviour.
    integrations: IntegrationRepositoryProtocol | None = None,
) -> JobResult:
    """`repo` and the retrieval collaborators are injected by the caller
    (the queue-factory closure, which opens one DB session for the job's
    duration) rather than constructed here — CLAUDE.md §11:
    dependency-injected clients are mockable via fakes, which is what
    lets this function's actual logic (bounds, status transitions, step
    recording, grounding) be unit-tested without a live Postgres
    connection or a real embedding provider.
    """
    run_id = job.payload.get("run_id")
    if not run_id:
        return JobResult.fail("agent_run job payload missing run_id")

    run = await repo.get_run(run_id)
    if run is None:
        return JobResult.fail(f"agent_run {run_id}: no such run")

    version = await repo.get_version(run.agent_version_id)
    if version is None:
        await repo.update_run_status(
            run_id=run_id, status="error", error_message="agent version not found"
        )
        return JobResult.fail(f"agent_run {run_id}: version {run.agent_version_id} not found")

    await repo.update_run_status(run_id=run_id, status="running")
    sequence = _SequenceCounter()
    await _record_and_publish_step(
        repo, redis, run=run, step_type="run_started", sequence=sequence, payload={}, cost=None
    )

    try:
        usage = await _execute(
            run=run,
            version=version,
            settings=settings,
            redis=redis,
            repo=repo,
            sequence=sequence,
            directory=directory,
            search=search,
            embedder=embedder,
            counter=counter,
            integrations=integrations,
        )
    except _RunAbortedError as exc:
        await repo.update_run_status(run_id=run_id, status="error", error_message=exc.reason)
        await _record_and_publish_step(
            repo,
            redis,
            run=run,
            step_type="run_failed",
            sequence=sequence,
            payload={"reason": exc.reason},
            cost=None,
        )
        return JobResult.ok({"run_id": run_id, "status": "error"})
    except Exception as exc:  # noqa: BLE001 - translated into a run failure, not a raw crash
        logger.exception("agent_run_job_failed run_id=%s", run_id)
        await repo.update_run_status(run_id=run_id, status="error", error_message=str(exc))
        await _record_and_publish_step(
            repo,
            redis,
            run=run,
            step_type="run_failed",
            sequence=sequence,
            payload={"reason": str(exc)},
            cost=None,
        )
        return JobResult.ok({"run_id": run_id, "status": "error"})

    total_cost = calculate_cost_micro_usd(version.config["model"], usage)
    await repo.update_run_status(run_id=run_id, status="success", cost_micro_usd=total_cost)
    await _record_and_publish_step(
        repo,
        redis,
        run=run,
        step_type="run_completed",
        sequence=sequence,
        payload={
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
        },
        cost=total_cost,
    )

    return JobResult.ok({"run_id": run_id, "status": "success"})


class _SequenceCounter:
    def __init__(self) -> None:
        self._value = 0

    def next(self) -> int:
        self._value += 1
        return self._value


async def _record_and_publish_step(
    repo: AgentRepositoryProtocol,
    redis: Redis,
    *,
    run: RunRecord,
    step_type: str,
    sequence: _SequenceCounter,
    payload: dict[str, Any],
    cost: int | None,
) -> None:
    """Persists the step and publishes the *identical* payload shape live
    (docs/systems/redis-channels.md: this is the first real consumer of
    the reserved `run:{run_id}:events` channel) — a live subscriber and a
    client backfilling from `agent_run_steps` after a reconnect see the
    same event shape either way, not two different representations of
    "what happened" that could drift apart.
    """
    seq = sequence.next()
    await repo.append_step(
        step_id=str(uuid.uuid4()),
        run_id=run.id,
        workspace_id=run.workspace_id,
        step_type=step_type,
        sequence=seq,
        payload=payload,
        cost_micro_usd=cost,
    )
    await publish_event(
        redis,
        run.id,
        {
            "type": step_type,
            "sequence": seq,
            "payload": payload,
            "cost_micro_usd": cost,
        },
    )


async def _execute(
    *,
    run: RunRecord,
    version: VersionRecord,
    settings: Settings,
    redis: Redis,
    repo: AgentRepositoryProtocol,
    sequence: _SequenceCounter,
    directory: KnowledgeBaseDirectory,
    search: ChunkSearchPort,
    embedder: EmbeddingProvider,
    counter: TokenCounter,
    #: Optional so every pre-Phase-6 caller and unit test keeps working
    #: unchanged: `None` means "this run has no MCP integrations", which
    #: is exactly the old behaviour.
    integrations: IntegrationRepositoryProtocol | None = None,
) -> TokenUsage:
    config = version.config
    prompt = run.input.get("prompt", "")

    # Grounding happens before the SDK `Agent` is constructed, because it
    # is what determines the agent's instructions. It never raises: a
    # failure degrades to the ungrounded prompt and reports itself in the
    # trace step below.
    grounding = await ground_run(
        query=prompt,
        system_instructions=config["system_instructions"],
        workspace_id=run.workspace_id,
        # `.get` rather than `[...]`: agent versions published before
        # Phase 5 have no `knowledge_base_ids` key at all, and a stored
        # config is data, not a schema that migrates itself.
        knowledge_base_ids=list(config.get("knowledge_base_ids") or []),
        model=config["model"],
        reserved_output_tokens=config.get("max_output_tokens") or _DEFAULT_RESERVED_OUTPUT_TOKENS,
        directory=directory,
        search=search,
        embedder=embedder,
        counter=counter,
    )
    if config.get("knowledge_base_ids"):
        # Emitted only when the agent actually has knowledge bases —
        # otherwise every ungrounded run would carry a noise step saying
        # nothing happened. When it *is* emitted it always appears, hit
        # or miss or failure, so "why did my agent ignore my documents?"
        # is answerable from the trace alone.
        await _record_and_publish_step(
            repo,
            redis,
            run=run,
            step_type="retrieval",
            sequence=sequence,
            payload={
                "citations": [
                    {
                        "chunk_id": c.chunk_id,
                        "kb_document_id": c.kb_document_id,
                        "knowledge_base_id": c.knowledge_base_id,
                        "chunk_index": c.chunk_index,
                    }
                    for c in grounding.citations
                ],
                "used_tokens": grounding.used_tokens,
                "dropped_chunk_count": grounding.dropped_chunk_count,
                "skipped_knowledge_base_ids": list(grounding.skipped_knowledge_base_ids),
                "error": grounding.error,
            },
            cost=None,
        )

    # MCP servers granted to this agent (Phase 6). Every one that
    # connects is wrapped in `GovernedMcpServer`, so the SDK never holds
    # a raw server object and no tool call can bypass the execution
    # boundary. A server that fails to connect disables only its own
    # tools and reports why in the trace — it never fails the run.
    attachment = await _attach_mcp(
        run=run, repo=repo, redis=redis, integrations=integrations, sequence=sequence
    )

    agent = Agent(
        name=f"agent-{run.agent_id}",
        instructions=grounding.instructions,
        model=config["model"],
        tools=resolve_tools(config.get("tools", [])),
        mcp_servers=attachment.servers,
        model_settings=ModelSettings(
            temperature=config.get("temperature"),
            max_tokens=config.get("max_output_tokens"),
        ),
    )

    try:
        result = Runner.run_streamed(agent, prompt, max_turns=settings.run_max_turns)
        start = time.monotonic()

        async for event in result.stream_events():
            if isinstance(event, RunItemStreamEvent):
                await _handle_run_item_event(
                    event, run=run, repo=repo, redis=redis, sequence=sequence
                )
            # raw_response_event token deltas are intentionally not
            # branched on here beyond the isinstance check above excluding
            # them — this phase publishes step-level events only; per-token
            # live deltas are a Phase 4 UI nicety, not a named acceptance
            # criterion, and are left for the SSE route (M4) to decide
            # whether to forward raw deltas at all.

            elapsed = time.monotonic() - start
            current_usage = TokenUsage(
                prompt_tokens=result.context_wrapper.usage.input_tokens,
                completion_tokens=result.context_wrapper.usage.output_tokens,
            )
            if elapsed > settings.run_timeout_seconds:
                result.cancel()
                raise _RunAbortedError(f"exceeded time budget of {settings.run_timeout_seconds}s")
            projected_cost = calculate_cost_micro_usd(config["model"], current_usage)
            if projected_cost > settings.run_cost_ceiling_micro_usd:
                result.cancel()
                ceiling = settings.run_cost_ceiling_micro_usd
                raise _RunAbortedError(f"exceeded cost ceiling of {ceiling} micro-USD")

        final_usage = result.context_wrapper.usage
        return TokenUsage(
            prompt_tokens=final_usage.input_tokens, completion_tokens=final_usage.output_tokens
        )
    finally:
        # MCP connections are per-run: a pooled session would outlive the
        # credential that opened it, so a revoked token would keep working
        # until the pool happened to evict it. Closed in `finally` because
        # a leaked stdio process or HTTP socket outlives the run that
        # needed it, whether or not the run succeeded.
        if attachment.manager is not None:
            await attachment.manager.aclose()


async def _attach_mcp(
    *,
    run: RunRecord,
    repo: AgentRepositoryProtocol,
    redis: Redis,
    integrations: IntegrationRepositoryProtocol | None,
    sequence: _SequenceCounter,
) -> AttachmentResult:
    """Resolves and connects this agent's MCP grants.

    Returns an empty attachment when no integration repository is wired
    (the pre-Phase-6 code path, and every unit test that does not care
    about MCP) — so the run behaves exactly as it did before rather than
    requiring every caller to know about integrations.
    """
    if integrations is None:
        return AttachmentResult()

    async def _emit(event_type: str, payload: dict[str, Any]) -> None:
        await _record_and_publish_step(
            repo,
            redis,
            run=run,
            step_type=event_type,
            sequence=sequence,
            payload=payload,
            cost=None,
        )

    resolved = await integrations.resolve_for_agent(
        workspace_id=run.workspace_id, agent_id=run.agent_id
    )
    if not resolved:
        return AttachmentResult()

    return await attach_integrations(
        resolved,
        context=ExecutionContext(
            workspace_id=run.workspace_id, run_id=run.id, agent_id=run.agent_id
        ),
        deps=BoundaryDeps(
            recorder=integrations,
            breaker=CircuitBreaker(redis),
            cache=ResultCache(redis),
            budget=CallBudget(redis),
        ),
        on_event=_emit,
    )


async def _handle_run_item_event(
    event: RunItemStreamEvent,
    *,
    run: RunRecord,
    repo: AgentRepositoryProtocol,
    redis: Redis,
    sequence: _SequenceCounter,
) -> None:
    if event.name == "message_output_created" and isinstance(event.item, MessageOutputItem):
        text = ItemHelpers.text_message_output(event.item)
        await _record_and_publish_step(
            repo,
            redis,
            run=run,
            step_type="llm_call",
            sequence=sequence,
            payload={"text": text},
            cost=None,
        )
    elif event.name == "tool_called" and isinstance(event.item, ToolCallItem):
        raw = event.item.raw_item
        name = getattr(raw, "name", None)
        arguments = getattr(raw, "arguments", None)
        await _record_and_publish_step(
            repo,
            redis,
            run=run,
            step_type="tool_call",
            sequence=sequence,
            payload={"phase": "called", "name": name, "arguments": arguments},
            cost=None,
        )
    elif event.name == "tool_output" and isinstance(event.item, ToolCallOutputItem):
        await _record_and_publish_step(
            repo,
            redis,
            run=run,
            step_type="tool_call",
            sequence=sequence,
            payload={"phase": "output", "output": str(event.item.output)},
            cost=None,
        )
