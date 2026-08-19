"""Executes a `workflow_node` job — one DAG node of a workflow run
(docs/roadmap.md Phase 10, docs/adr/0016).

The core design rule: an `agent_step`/`team_step` node never
reimplements execution — it calls `handle_agent_run_job`/
`handle_team_session_job` directly, in-process, the exact same tested
functions the queue calls for a standalone run. Durability comes from
the `agent_runs`/`team_sessions` row itself (written before this
function returns), not from anything held in worker memory: if this job
crashes after the sub-run finished but before the DAG advanced,
redelivery finds the terminal `workflow_node_runs` row and advances
straight from there without re-executing (Rule 14).

`conditional_branch`/`parallel_fanout`/`human_approval` nodes execute no
sub-run at all — they are pure DAG-shaping decisions made here.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from agentverse_shared.embeddings.port import EmbeddingProvider
from agentverse_shared.retrieval.port import ChunkSearchPort
from agentverse_shared.text.tokenizer import TokenCounter
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentverse_worker.agents.grounding import KnowledgeBaseDirectory
from agentverse_worker.agents.repository import AgentRepositoryProtocol
from agentverse_worker.infrastructure.config import Settings
from agentverse_worker.jobs.agent_run_job import handle_agent_run_job
from agentverse_worker.jobs.team_session_job import handle_team_session_job
from agentverse_worker.mcp.repository import IntegrationRepositoryProtocol
from agentverse_worker.queue.models import Job, JobResult
from agentverse_worker.queue.producer import enqueue
from agentverse_worker.teams.repository import TeamRepositoryProtocol
from agentverse_worker.workflows.graph_runtime import (
    DEFAULT_INPUT_TEMPLATE,
    evaluate_condition,
    ordered_outgoing_edges,
    resolve_input_template,
)
from agentverse_worker.workflows.repository import (
    WorkflowEdgeRecord,
    WorkflowNodeRecord,
    WorkflowNodeRunRecord,
    WorkflowRepositoryProtocol,
    WorkflowRunRecord,
)

logger = logging.getLogger(__name__)

_TERMINAL_RUN_STATUSES = frozenset({"success", "error", "cancelled"})
_ACTIVE_NODE_RUN_STATUSES = frozenset({"queued", "running", "paused_for_approval"})


class WorkflowExecutionDeps:
    """Everything a node execution might need, bundled once by the queue
    factory — the same collaborators `handle_agent_run_job`/
    `handle_team_session_job` already require, plus this engine's own
    workflow repository and the stream to chain the next node's job onto.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        redis: Redis,
        queue_stream: str,
        workflow_repo: WorkflowRepositoryProtocol,
        agent_repo: AgentRepositoryProtocol,
        team_repo: TeamRepositoryProtocol,
        directory: KnowledgeBaseDirectory,
        search: ChunkSearchPort,
        embedder: EmbeddingProvider,
        counter: TokenCounter,
        integrations: IntegrationRepositoryProtocol | None,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.settings = settings
        self.redis = redis
        self.queue_stream = queue_stream
        self.workflow_repo = workflow_repo
        self.agent_repo = agent_repo
        self.team_repo = team_repo
        self.directory = directory
        self.search = search
        self.embedder = embedder
        self.counter = counter
        self.integrations = integrations
        self.session_factory = session_factory


async def handle_workflow_node_job(job: Job, *, deps: WorkflowExecutionDeps) -> JobResult:
    workflow_run_id = job.payload.get("workflow_run_id")
    node_id = job.payload.get("node_id")
    if not workflow_run_id or not node_id:
        return JobResult.fail("workflow_node job payload missing workflow_run_id/node_id")

    run = await deps.workflow_repo.get_run(workflow_run_id)
    if run is None:
        return JobResult.fail(f"workflow_node: no such workflow_run {workflow_run_id}")
    if run.status in _TERMINAL_RUN_STATUSES:
        # The overall run already finished (e.g. a sibling branch failed
        # and ended it) — a stray/redelivered job for a dead run.
        return JobResult.ok({"workflow_run_id": workflow_run_id, "status": run.status})

    nodes, edges = await deps.workflow_repo.get_nodes_and_edges(run.workflow_version_id)
    node = next((n for n in nodes if n.id == node_id), None)
    if node is None:
        return JobResult.fail(f"workflow_node: node {node_id} not found")

    node_run = await deps.workflow_repo.get_node_run(
        workflow_run_id=workflow_run_id, node_id=node_id
    )
    if node_run is not None and node_run.status == "paused_for_approval":
        # Waiting on a human — the `/resolve` route drives this forward,
        # not another delivery of this same job.
        return JobResult.ok(_result(workflow_run_id, node_id, node_run.status))

    if node_run is None or not node_run.is_terminal():
        node_run = await _execute_node(node, node_run, run, deps=deps)

    if node_run.status == "paused_for_approval":
        return JobResult.ok(_result(workflow_run_id, node_id, node_run.status))

    await _advance(node=node, node_run=node_run, edges=edges, run=run, deps=deps)
    return JobResult.ok(_result(workflow_run_id, node_id, node_run.status))


def _result(workflow_run_id: str, node_id: str, status: str) -> dict[str, Any]:
    return {"workflow_run_id": workflow_run_id, "node_id": node_id, "status": status}


async def _execute_node(
    node: WorkflowNodeRecord,
    existing_node_run: WorkflowNodeRunRecord | None,
    run: WorkflowRunRecord,
    *,
    deps: WorkflowExecutionDeps,
) -> WorkflowNodeRunRecord:
    if existing_node_run is not None:
        # Reuses the row left by a prior attempt that crashed mid-flight
        # (still `running`) rather than creating a second row for the
        # same (workflow_run_id, node_id) pair — `get_node_run` assumes
        # exactly one.
        node_run = existing_node_run
    else:
        sequence = len(await deps.workflow_repo.list_node_runs(workflow_run_id=run.id)) + 1
        node_run = await deps.workflow_repo.create_node_run(
            workflow_run_id=run.id, node_id=node.id, status="running", sequence=sequence
        )

    if node.type == "agent_step":
        return await _execute_agent_step(node, node_run, run, deps=deps)
    if node.type == "team_step":
        return await _execute_team_step(node, node_run, run, deps=deps)
    if node.type == "human_approval":
        await deps.workflow_repo.update_node_run(
            node_run_id=node_run.id, status="paused_for_approval"
        )
        await deps.workflow_repo.update_run_status(run_id=run.id, status="paused")
        return _with(node_run, status="paused_for_approval")
    # conditional_branch / parallel_fanout: pure routing, no sub-run.
    await deps.workflow_repo.update_node_run(node_run_id=node_run.id, status="success")
    return _with(node_run, status="success")


async def _node_outputs_by_id(
    run: WorkflowRunRecord, *, deps: WorkflowExecutionDeps
) -> dict[str, str]:
    node_runs = await deps.workflow_repo.list_node_runs(workflow_run_id=run.id)
    outputs: dict[str, str] = {}
    for nr in node_runs:
        if nr.output and isinstance(nr.output.get("text"), str):
            outputs[nr.node_id] = nr.output["text"]
    return outputs


async def _execute_agent_step(
    node: WorkflowNodeRecord,
    node_run: WorkflowNodeRunRecord,
    run: WorkflowRunRecord,
    *,
    deps: WorkflowExecutionDeps,
) -> WorkflowNodeRunRecord:
    # Enforced by the DB CHECK constraint on this node type.
    assert node.agent_id is not None  # noqa: S101
    version_id = await deps.agent_repo.get_published_version_id(node.agent_id)
    if version_id is None:
        await deps.workflow_repo.update_node_run(node_run_id=node_run.id, status="error")
        return _with(node_run, status="error")

    template = str(node.config.get("input_template") or DEFAULT_INPUT_TEMPLATE)
    prompt = resolve_input_template(
        template,
        trigger_input=str(run.input.get("prompt", "")),
        node_outputs=await _node_outputs_by_id(run, deps=deps),
    )
    agent_run = await deps.agent_repo.create_run(
        workspace_id=run.workspace_id,
        agent_id=node.agent_id,
        agent_version_id=version_id,
        input={"prompt": prompt},
    )
    sub_job = Job(
        job_id=str(uuid.uuid4()),
        job_type="agent_run",
        payload={"run_id": agent_run.id},
        attempt=0,
        max_attempts=1,
    )
    await handle_agent_run_job(
        sub_job,
        settings=deps.settings,
        redis=deps.redis,
        repo=deps.agent_repo,
        directory=deps.directory,
        search=deps.search,
        embedder=deps.embedder,
        counter=deps.counter,
        integrations=deps.integrations,
    )
    final_run = await deps.agent_repo.get_run(agent_run.id)
    status = final_run.status if final_run is not None else "error"
    output_text = await deps.agent_repo.get_final_output(agent_run.id)
    output = {"text": output_text} if output_text is not None else None
    if final_run is not None and final_run.cost_micro_usd:
        await deps.workflow_repo.add_run_cost(
            run_id=run.id, delta_micro_usd=final_run.cost_micro_usd
        )
    await deps.workflow_repo.update_node_run(
        node_run_id=node_run.id, status=status, output=output, agent_run_id=agent_run.id
    )
    return _with(node_run, status=status, output=output, agent_run_id=agent_run.id)


async def _execute_team_step(
    node: WorkflowNodeRecord,
    node_run: WorkflowNodeRunRecord,
    run: WorkflowRunRecord,
    *,
    deps: WorkflowExecutionDeps,
) -> WorkflowNodeRunRecord:
    # Enforced by the DB CHECK constraint on this node type.
    assert node.team_id is not None  # noqa: S101
    template = str(node.config.get("input_template") or DEFAULT_INPUT_TEMPLATE)
    prompt = resolve_input_template(
        template,
        trigger_input=str(run.input.get("prompt", "")),
        node_outputs=await _node_outputs_by_id(run, deps=deps),
    )
    session = await deps.team_repo.create_session(
        workspace_id=run.workspace_id, team_id=node.team_id, input={"prompt": prompt}
    )
    sub_job = Job(
        job_id=str(uuid.uuid4()),
        job_type="team_session",
        payload={"session_id": session.id},
        attempt=0,
        max_attempts=1,
    )
    await handle_team_session_job(
        sub_job, redis=deps.redis, repo=deps.team_repo, session_factory=deps.session_factory
    )
    final_session = await deps.team_repo.get_session(session.id)
    status = final_session.status if final_session is not None else "error"
    output = {"text": final_session.output} if final_session and final_session.output else None
    if final_session is not None and final_session.cost_micro_usd:
        await deps.workflow_repo.add_run_cost(
            run_id=run.id, delta_micro_usd=final_session.cost_micro_usd
        )
    await deps.workflow_repo.update_node_run(
        node_run_id=node_run.id, status=status, output=output, team_session_id=session.id
    )
    return _with(node_run, status=status, output=output, team_session_id=session.id)


def _with(
    node_run: WorkflowNodeRunRecord,
    *,
    status: str,
    output: dict[str, Any] | None = None,
    agent_run_id: str | None = None,
    team_session_id: str | None = None,
) -> WorkflowNodeRunRecord:
    return WorkflowNodeRunRecord(
        id=node_run.id,
        workflow_run_id=node_run.workflow_run_id,
        node_id=node_run.node_id,
        status=status,
        output=output if output is not None else node_run.output,
        agent_run_id=agent_run_id or node_run.agent_run_id,
        team_session_id=team_session_id or node_run.team_session_id,
        sequence=node_run.sequence,
    )


async def _advance(
    *,
    node: WorkflowNodeRecord,
    node_run: WorkflowNodeRunRecord,
    edges: list[WorkflowEdgeRecord],
    run: WorkflowRunRecord,
    deps: WorkflowExecutionDeps,
) -> None:
    if node_run.status == "error":
        await deps.workflow_repo.update_run_status(
            run_id=run.id, status="error", error_message=f"node {node.id} failed"
        )
        return

    outgoing = ordered_outgoing_edges(edges, from_node_id=node.id)
    targets: list[str]
    if node.type == "conditional_branch":
        predecessor_output = await _predecessor_output(node.id, edges=edges, run=run, deps=deps)
        matched = next(
            (e for e in outgoing if evaluate_condition(e.condition, predecessor_output)), None
        )
        targets = [matched.to_node_id] if matched is not None else []
    else:
        targets = [e.to_node_id for e in outgoing]

    for target_id in targets:
        await enqueue(
            deps.redis,
            stream=deps.queue_stream,
            job_type="workflow_node",
            payload={"workflow_run_id": run.id, "node_id": target_id},
        )

    if not targets:
        # A leaf on this branch. If nothing else in this run is still
        # in flight, the whole workflow run is done.
        all_node_runs = await deps.workflow_repo.list_node_runs(workflow_run_id=run.id)
        still_active = any(nr.status in _ACTIVE_NODE_RUN_STATUSES for nr in all_node_runs)
        if not still_active:
            await deps.workflow_repo.update_run_status(run_id=run.id, status="success")


async def _predecessor_output(
    node_id: str,
    *,
    edges: list[WorkflowEdgeRecord],
    run: WorkflowRunRecord,
    deps: WorkflowExecutionDeps,
) -> dict[str, Any] | None:
    incoming = next((e for e in edges if e.to_node_id == node_id), None)
    if incoming is None:
        return None
    predecessor_run = await deps.workflow_repo.get_node_run(
        workflow_run_id=run.id, node_id=incoming.from_node_id
    )
    return predecessor_run.output if predecessor_run is not None else None
