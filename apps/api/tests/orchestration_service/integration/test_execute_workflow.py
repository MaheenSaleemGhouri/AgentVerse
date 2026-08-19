"""Workflow-run submission against real Postgres + Redis.

Integration because the guarantee that matters is the DB/Redis one: row
created before the job is enqueued, and idempotent resubmission never
double-enqueues (mirrors `tests/billing_service/integration/test_credits.
py`'s framing — a fake can be made to obey this trivially).
"""

from __future__ import annotations

import uuid

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.orchestration_service.application.execute_workflow import execute_workflow
from agentverse_api.orchestration_service.domain.workflow_entities import (
    WorkflowNode,
    WorkflowNodeType,
)
from agentverse_api.orchestration_service.domain.workflow_exceptions import (
    WorkflowNotRunnableError,
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


class _FakeLock:
    async def acquire(self) -> bool:
        return True

    async def release(self) -> None:
        return None


async def _workspace(session: AsyncSession) -> str:
    workspace_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO workspaces (id, name, slug, created_at) "
            "VALUES (:id, 'Exec WF', :slug, now())"
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
            "VALUES (:id, :email, 'Exec Tester', true, now(), now())"
        ),
        {"id": user_id, "email": f"exec-{user_id[:8]}@example.test"},
    )
    await session.flush()
    return user_id


async def _published_workflow(session: AsyncSession, *, workspace_id: str, user_id: str) -> str:
    repo = SqlWorkflowRepository(session)
    workflow, _ = await repo.create_workflow(
        workspace_id=workspace_id, name="Runnable", description=None, created_by_user_id=user_id
    )
    node = WorkflowNode(
        id=str(uuid.uuid4()), type=WorkflowNodeType.PARALLEL_FANOUT, position_x=0, position_y=0,
        config={},
    )
    version = await repo.create_version(
        workflow_id=workflow.id, nodes=[node], edges=[], created_by_user_id=user_id
    )
    await repo.publish_version(workflow_id=workflow.id, version_id=version.id)
    return workflow.id


async def test_execute_workflow_creates_run_and_enqueues_start_node(
    db_session: AsyncSession, fake_redis: Redis
) -> None:
    workspace_id = await _workspace(db_session)
    user_id = await _user(db_session)
    workflow_id = await _published_workflow(db_session, workspace_id=workspace_id, user_id=user_id)
    producer = JobQueueProducer(fake_redis, stream="queue:jobs:test-exec")

    run = await execute_workflow(
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        input={"prompt": "go"},
        idempotency_key=None,
        workflow_repo=SqlWorkflowRepository(db_session),
        run_repo=SqlWorkflowRunRepository(db_session),
        producer=producer,
        lock_factory=lambda _key: _FakeLock(),
    )

    assert run.status.value == "queued"
    assert await fake_redis.xlen("queue:jobs:test-exec") == 1
    await db_session.rollback()


async def test_idempotency_key_reuse_does_not_double_enqueue(
    db_session: AsyncSession, fake_redis: Redis
) -> None:
    workspace_id = await _workspace(db_session)
    user_id = await _user(db_session)
    workflow_id = await _published_workflow(db_session, workspace_id=workspace_id, user_id=user_id)
    producer = JobQueueProducer(fake_redis, stream="queue:jobs:test-idem")

    kwargs = dict(
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        input={"prompt": "go"},
        idempotency_key="fixed-key",
        workflow_repo=SqlWorkflowRepository(db_session),
        run_repo=SqlWorkflowRunRepository(db_session),
        producer=producer,
        lock_factory=lambda _key: _FakeLock(),
    )
    first = await execute_workflow(**kwargs)  # type: ignore[arg-type]
    second = await execute_workflow(**kwargs)  # type: ignore[arg-type]

    assert first.id == second.id
    assert await fake_redis.xlen("queue:jobs:test-idem") == 1
    await db_session.rollback()


async def test_unpublished_workflow_is_not_runnable(
    db_session: AsyncSession, fake_redis: Redis
) -> None:
    workspace_id = await _workspace(db_session)
    user_id = await _user(db_session)
    repo = SqlWorkflowRepository(db_session)
    workflow, _ = await repo.create_workflow(
        workspace_id=workspace_id, name="Draft", description=None, created_by_user_id=user_id
    )
    producer = JobQueueProducer(fake_redis, stream="queue:jobs:test-unpub")

    with pytest.raises(WorkflowNotRunnableError):
        await execute_workflow(
            workspace_id=workspace_id,
            workflow_id=workflow.id,
            input={},
            idempotency_key=None,
            workflow_repo=repo,
            run_repo=SqlWorkflowRunRepository(db_session),
            producer=producer,
            lock_factory=lambda _key: _FakeLock(),
        )
    await db_session.rollback()
