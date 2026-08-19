"""Workflow authoring against real Postgres.

These run as integration tests because the guarantees that matter are
database ones: the FK from `workflow_nodes.agent_id` to `agents.id` (the
structural "a node delegates to Phase 9" guarantee), the CHECK
constraint on node type/agent_id/team_id consistency, and cross-workspace
isolation. A fake repository can be written to obey all of these, which
is exactly why proving them against a fake proves nothing
(mirrors `tests/billing_service/integration/test_credits.py`'s framing).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.orchestration_service.application.create_workflow_version import (
    create_workflow_version,
)
from agentverse_api.orchestration_service.domain.workflow_entities import (
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeType,
    WorkflowStatus,
)
from agentverse_api.orchestration_service.domain.workflow_exceptions import (
    InvalidWorkflowGraphError,
)
from agentverse_api.orchestration_service.infrastructure.workflow_repository import (
    SqlWorkflowRepository,
)


async def _workspace(session: AsyncSession) -> str:
    workspace_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO workspaces (id, name, slug, created_at) "
            "VALUES (:id, 'WF Test', :slug, now())"
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
            "VALUES (:id, :email, 'WF Tester', true, now(), now())"
        ),
        {"id": user_id, "email": f"wf-{user_id[:8]}@example.test"},
    )
    await session.flush()
    return user_id


async def _agent(session: AsyncSession, *, workspace_id: str, user_id: str) -> str:
    agent_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO agents (id, workspace_id, name, status, created_by_user_id, "
            "created_at, updated_at) "
            "VALUES (:id, :ws, 'WF Test Agent', 'active', :user, now(), now())"
        ),
        {"id": agent_id, "ws": workspace_id, "user": user_id},
    )
    await session.flush()
    return agent_id


async def test_create_workflow_creates_an_empty_first_version(db_session: AsyncSession) -> None:
    workspace_id = await _workspace(db_session)
    user_id = await _user(db_session)
    repo = SqlWorkflowRepository(db_session)

    workflow, version = await repo.create_workflow(
        workspace_id=workspace_id, name="Onboarding", description=None, created_by_user_id=user_id
    )

    assert workflow.status is WorkflowStatus.DRAFT
    assert workflow.published_version_id is None
    assert version.version_number == 1
    assert version.nodes == []
    assert version.edges == []
    await db_session.rollback()


async def test_create_version_round_trips_nodes_and_edges(db_session: AsyncSession) -> None:
    workspace_id = await _workspace(db_session)
    user_id = await _user(db_session)
    agent_id = await _agent(db_session, workspace_id=workspace_id, user_id=user_id)
    repo = SqlWorkflowRepository(db_session)
    workflow, _ = await repo.create_workflow(
        workspace_id=workspace_id, name="Triage", description=None, created_by_user_id=user_id
    )

    start = WorkflowNode(
        id=str(uuid.uuid4()),
        type=WorkflowNodeType.AGENT_STEP,
        position_x=10,
        position_y=20,
        config={"input_template": "{{trigger.input}}"},
        agent_id=agent_id,
    )
    approval = WorkflowNode(
        id=str(uuid.uuid4()),
        type=WorkflowNodeType.HUMAN_APPROVAL,
        position_x=200,
        position_y=20,
        config={"message": "Approve this triage result?"},
    )
    edge = WorkflowEdge(id=str(uuid.uuid4()), from_node_id=start.id, to_node_id=approval.id)

    version = await create_workflow_version(
        workflow_id=workflow.id,
        nodes=[start, approval],
        edges=[edge],
        created_by_user_id=user_id,
        workflow_repo=repo,
    )
    assert version.version_number == 2  # version 1 is the empty draft from create_workflow

    fetched = await repo.get_latest_version(workflow_id=workflow.id)
    assert fetched is not None
    assert {n.id for n in fetched.nodes} == {start.id, approval.id}
    assert fetched.edges[0].from_node_id == start.id
    assert fetched.edges[0].to_node_id == approval.id
    fetched_start = fetched.node_by_id(start.id)
    assert fetched_start is not None
    assert fetched_start.agent_id == agent_id
    assert fetched_start.config == {"input_template": "{{trigger.input}}"}
    await db_session.rollback()


async def test_publish_version_sets_the_pointer_and_activates(db_session: AsyncSession) -> None:
    workspace_id = await _workspace(db_session)
    user_id = await _user(db_session)
    repo = SqlWorkflowRepository(db_session)
    workflow, version = await repo.create_workflow(
        workspace_id=workspace_id, name="Publish Me", description=None, created_by_user_id=user_id
    )

    published = await repo.publish_version(workflow_id=workflow.id, version_id=version.id)

    assert published.published_version_id == version.id
    assert published.status is WorkflowStatus.ACTIVE
    await db_session.rollback()


async def test_workspaces_cannot_see_each_others_workflows(db_session: AsyncSession) -> None:
    ws_a = await _workspace(db_session)
    ws_b = await _workspace(db_session)
    user_id = await _user(db_session)
    repo = SqlWorkflowRepository(db_session)
    workflow, _ = await repo.create_workflow(
        workspace_id=ws_a, name="Private to A", description=None, created_by_user_id=user_id
    )

    assert await repo.get_workflow(workspace_id=ws_b, workflow_id=workflow.id) is None
    assert workflow.id not in {w.id for w in await repo.list_workflows(workspace_id=ws_b)}
    assert workflow.id in {w.id for w in await repo.list_workflows(workspace_id=ws_a)}
    await db_session.rollback()


async def test_invalid_graph_is_rejected_before_anything_is_persisted(
    db_session: AsyncSession,
) -> None:
    workspace_id = await _workspace(db_session)
    user_id = await _user(db_session)
    repo = SqlWorkflowRepository(db_session)
    workflow, _ = await repo.create_workflow(
        workspace_id=workspace_id, name="Bad Graph", description=None, created_by_user_id=user_id
    )

    a = WorkflowNode(
        id=str(uuid.uuid4()), type=WorkflowNodeType.PARALLEL_FANOUT, position_x=0, position_y=0,
        config={},
    )
    b = WorkflowNode(
        id=str(uuid.uuid4()), type=WorkflowNodeType.PARALLEL_FANOUT, position_x=0, position_y=0,
        config={},
    )
    # A cycle: a -> b -> a.
    cycle_edges = [
        WorkflowEdge(id=str(uuid.uuid4()), from_node_id=a.id, to_node_id=b.id),
        WorkflowEdge(id=str(uuid.uuid4()), from_node_id=b.id, to_node_id=a.id),
    ]

    with pytest.raises(InvalidWorkflowGraphError):
        await create_workflow_version(
            workflow_id=workflow.id,
            nodes=[a, b],
            edges=cycle_edges,
            created_by_user_id=user_id,
            workflow_repo=repo,
        )

    # Nothing was written: the workflow still only has its empty draft.
    latest = await repo.get_latest_version(workflow_id=workflow.id)
    assert latest is not None
    assert latest.version_number == 1
    await db_session.rollback()


async def test_node_target_check_constraint_rejects_mismatched_agent_step(
    db_session: AsyncSession,
) -> None:
    """Defense-in-depth: even bypassing the pure `validate_workflow_graph`
    check (calling `create_version` directly), the DB CHECK constraint
    on `workflow_nodes` refuses an agent_step node with no agent_id.
    """
    workspace_id = await _workspace(db_session)
    user_id = await _user(db_session)
    repo = SqlWorkflowRepository(db_session)
    workflow, _ = await repo.create_workflow(
        workspace_id=workspace_id, name="Bypass", description=None, created_by_user_id=user_id
    )

    bad_node = WorkflowNode(
        id=str(uuid.uuid4()), type=WorkflowNodeType.AGENT_STEP, position_x=0, position_y=0,
        config={}, agent_id=None,
    )

    with pytest.raises(IntegrityError):
        await repo.create_version(
            workflow_id=workflow.id, nodes=[bad_node], edges=[], created_by_user_id=user_id
        )
    await db_session.rollback()
