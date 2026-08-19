"""Approval resolution against real Postgres + Redis — the resume half
of durable human-in-the-loop pause (docs/adr/0016).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.orchestration_service.application.resolve_workflow_approval import (
    NodeNotPausedError,
    resolve_workflow_approval,
)
from agentverse_api.orchestration_service.domain.workflow_entities import (
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeType,
)
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)
from agentverse_api.orchestration_service.infrastructure.workflow_repository import (
    SqlWorkflowRepository,
)
from agentverse_api.orchestration_service.infrastructure.workflow_run_repository import (
    SqlWorkflowRunRepository,
)


async def _workspace(session: AsyncSession) -> str:
    workspace_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO workspaces (id, name, slug, created_at) "
            "VALUES (:id, 'Resolve WF', :slug, now())"
        ),
        {"id": workspace_id, "slug": f"ws-{workspace_id[:8]}"},
    )
    await session.flush()
    return workspace_id


async def _user(session: AsyncSession) -> str:
    user_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO users (id, email, name, email_verified, created_at, updated_at) "
            "VALUES (:id, :email, 'Resolve Tester', true, now(), now())"
        ),
        {"id": user_id, "email": f"resolve-{user_id[:8]}@example.test"},
    )
    await session.flush()
    return user_id


async def _paused_run(
    session: AsyncSession, *, workspace_id: str, user_id: str, second_edge: bool
) -> dict[str, str]:
    """A two-node workflow (`human_approval` -> `parallel_fanout`),
    published, with a run whose approval node is already paused.
    """
    repo = SqlWorkflowRepository(session)
    workflow, _ = await repo.create_workflow(
        workspace_id=workspace_id, name="Approval Flow", description=None,
        created_by_user_id=user_id,
    )
    approval_id = str(uuid.uuid4())
    next_id = str(uuid.uuid4())
    nodes = [
        WorkflowNode(
            id=approval_id, type=WorkflowNodeType.HUMAN_APPROVAL, position_x=0, position_y=0,
            config={},
        ),
        WorkflowNode(
            id=next_id, type=WorkflowNodeType.PARALLEL_FANOUT, position_x=100, position_y=0,
            config={},
        ),
    ]
    edges = (
        [WorkflowEdge(id=str(uuid.uuid4()), from_node_id=approval_id, to_node_id=next_id)]
        if second_edge
        else []
    )
    version = await repo.create_version(
        workflow_id=workflow.id, nodes=nodes, edges=edges, created_by_user_id=user_id
    )
    await repo.publish_version(workflow_id=workflow.id, version_id=version.id)

    run_repo = SqlWorkflowRunRepository(session)
    run = await run_repo.create_run(
        workspace_id=workspace_id, workflow_id=workflow.id, workflow_version_id=version.id,
        input={}, idempotency_key=None,
    )
    # Only the API-side repo exists here — node_run creation is a
    # worker-engine concern (`WorkerWorkflowRepository.create_node_run`),
    # so this seeds the paused row directly, matching how the real
    # engine would have left it.
    node_run_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO workflow_node_runs (id, created_at, workflow_run_id, node_id, status, "
            " sequence) VALUES (:id, :now, :run, :node, 'paused_for_approval', 1)"
        ),
        {"id": node_run_id, "now": datetime.now(UTC), "run": run.id, "node": approval_id},
    )
    await run_repo.update_run_status(run_id=run.id, status="paused")
    await session.flush()
    return {"workflow_id": workflow.id, "run_id": run.id, "node_id": approval_id}


async def test_approval_enqueues_the_next_node_and_resumes_the_run(
    db_session: AsyncSession, fake_redis: Redis
) -> None:
    workspace_id = await _workspace(db_session)
    user_id = await _user(db_session)
    ctx = await _paused_run(
        db_session, workspace_id=workspace_id, user_id=user_id, second_edge=True
    )
    producer = JobQueueProducer(fake_redis, stream="queue:jobs:test-approve")

    resolved = await resolve_workflow_approval(
        workspace_id=workspace_id,
        workflow_id=ctx["workflow_id"],
        run_id=ctx["run_id"],
        node_id=ctx["node_id"],
        decision="approved",
        approved_by_user_id=user_id,
        workflow_repo=SqlWorkflowRepository(db_session),
        run_repo=SqlWorkflowRunRepository(db_session),
        producer=producer,
    )

    assert resolved.status.value == "success"
    assert resolved.approval_decision == "approved"
    assert await fake_redis.xlen("queue:jobs:test-approve") == 1

    run_repo = SqlWorkflowRunRepository(db_session)
    run = await run_repo.get_run(workspace_id=workspace_id, run_id=ctx["run_id"])
    assert run is not None
    assert run.status.value == "running"
    await db_session.rollback()


async def test_rejection_ends_the_run_without_enqueueing(
    db_session: AsyncSession, fake_redis: Redis
) -> None:
    workspace_id = await _workspace(db_session)
    user_id = await _user(db_session)
    ctx = await _paused_run(
        db_session, workspace_id=workspace_id, user_id=user_id, second_edge=True
    )
    producer = JobQueueProducer(fake_redis, stream="queue:jobs:test-reject")

    resolved = await resolve_workflow_approval(
        workspace_id=workspace_id,
        workflow_id=ctx["workflow_id"],
        run_id=ctx["run_id"],
        node_id=ctx["node_id"],
        decision="rejected",
        approved_by_user_id=user_id,
        workflow_repo=SqlWorkflowRepository(db_session),
        run_repo=SqlWorkflowRunRepository(db_session),
        producer=producer,
    )

    assert resolved.status.value == "error"
    assert await fake_redis.xlen("queue:jobs:test-reject") == 0

    run_repo = SqlWorkflowRunRepository(db_session)
    run = await run_repo.get_run(workspace_id=workspace_id, run_id=ctx["run_id"])
    assert run is not None
    assert run.status.value == "error"
    await db_session.rollback()


async def test_resolving_a_node_that_is_not_paused_is_rejected(
    db_session: AsyncSession, fake_redis: Redis
) -> None:
    workspace_id = await _workspace(db_session)
    user_id = await _user(db_session)
    ctx = await _paused_run(
        db_session, workspace_id=workspace_id, user_id=user_id, second_edge=False
    )
    producer = JobQueueProducer(fake_redis, stream="queue:jobs:test-notpaused")

    await resolve_workflow_approval(
        workspace_id=workspace_id, workflow_id=ctx["workflow_id"], run_id=ctx["run_id"],
        node_id=ctx["node_id"], decision="approved", approved_by_user_id=user_id,
        workflow_repo=SqlWorkflowRepository(db_session),
        run_repo=SqlWorkflowRunRepository(db_session),
        producer=producer,
    )

    with pytest.raises(NodeNotPausedError):
        await resolve_workflow_approval(
            workspace_id=workspace_id, workflow_id=ctx["workflow_id"], run_id=ctx["run_id"],
            node_id=ctx["node_id"], decision="approved", approved_by_user_id=user_id,
            workflow_repo=SqlWorkflowRepository(db_session),
            run_repo=SqlWorkflowRunRepository(db_session), producer=producer,
        )
    await db_session.rollback()
