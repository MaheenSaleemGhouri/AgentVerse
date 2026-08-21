"""Support tickets against real Postgres — cross-workspace isolation
(Rule 11) and the triage-result read path, which composes real
`orchestration_service` rows (`agents`/`agent_versions`/`agent_runs`/
`agent_run_steps`) the same way `run_agent` and a worker actually would.

No worker runs in this test process, so `create_ticket` only gets as far
as *enqueuing* a run — the "run finished" half of the read path
(`get_ticket` resolving TRIAGED/FAILED) is exercised by advancing the
run's own rows directly, standing in for what `apps/worker`'s
`agent_run_job.py` would otherwise do.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.orchestration_service.domain.agent_entities import AgentConfig
from agentverse_api.orchestration_service.domain.run_entities import AgentRunStep, RunStatus
from agentverse_api.orchestration_service.infrastructure.repositories import (
    SqlAgentRepository,
    SqlAgentRunRepository,
)
from agentverse_api.support_service.application.support_ticket_service import (
    SupportTicketService,
)
from agentverse_api.support_service.domain.entities import TicketStatus
from agentverse_api.support_service.infrastructure.repositories import SqlSupportTicketRepository

pytestmark = pytest.mark.integration


class _NullProducer:
    """Stands in for `JobQueueProducer`: no real Redis stream in this
    test, and nothing here needs the enqueue to actually reach a queue —
    only that `create_ticket` completes and records the run id.
    """

    async def enqueue_agent_run(self, *, run_id: str) -> None:
        del run_id


class _ImmediateLock:
    async def acquire(self) -> bool:
        return True

    async def release(self) -> None:
        return None


def _lock_factory(key: str) -> _ImmediateLock:
    del key
    return _ImmediateLock()


async def _workspace(session: AsyncSession) -> str:
    workspace_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO workspaces (id, name, slug, created_at) VALUES (:id, :name, :slug, now())"
        ),
        {"id": workspace_id, "name": "Support Test", "slug": f"ws-{workspace_id[:8]}"},
    )
    await session.flush()
    return workspace_id


async def _user(session: AsyncSession) -> str:
    user_id = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO users (id, name, email, email_verified, created_at, updated_at) "
            "VALUES (:id, 'Triage Tester', :email, true, now(), now())"
        ),
        {"id": user_id, "email": f"{user_id[:8]}@example.test"},
    )
    await session.flush()
    return user_id


async def _runnable_agent(session: AsyncSession, workspace_id: str, user_id: str) -> str:
    repo = SqlAgentRepository(session)
    agent, version = await repo.create_agent(
        workspace_id=workspace_id,
        name="Support Triage",
        description=None,
        created_by_user_id=user_id,
        initial_config=AgentConfig(
            model="gpt-4o-mini",
            system_instructions="You triage support tickets.",
        ),
    )
    await repo.publish_version(agent_id=agent.id, version_id=version.id)
    return agent.id


def _service(session: AsyncSession) -> SupportTicketService:
    return SupportTicketService(
        tickets=SqlSupportTicketRepository(session),
        agent_repo=SqlAgentRepository(session),
        run_repo=SqlAgentRunRepository(session),
        producer=_NullProducer(),  # type: ignore[arg-type]
        lock_factory=_lock_factory,
    )


class TestCreateTicket:
    async def test_creating_a_ticket_enqueues_a_real_run(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        user_id = await _user(db_session)
        agent_id = await _runnable_agent(db_session, workspace_id, user_id)
        service = _service(db_session)

        ticket = await service.create_ticket(
            workspace_id=workspace_id,
            agent_id=agent_id,
            subject="Can't log in",
            body="I get an error on the login page.",
            created_by_user_id=user_id,
            idempotency_key=None,
        )

        assert ticket.status is TicketStatus.TRIAGING
        assert ticket.triage_run_id is not None
        run = await SqlAgentRunRepository(db_session).get_run(
            workspace_id=workspace_id, run_id=ticket.triage_run_id
        )
        assert run is not None
        assert run.input["prompt"] == "Subject: Can't log in\n\nI get an error on the login page."
        await db_session.rollback()


class TestWorkspaceIsolation:
    async def test_a_ticket_is_invisible_to_another_workspace(
        self, db_session: AsyncSession
    ) -> None:
        owner_workspace = await _workspace(db_session)
        stranger_workspace = await _workspace(db_session)
        user_id = await _user(db_session)
        agent_id = await _runnable_agent(db_session, owner_workspace, user_id)
        service = _service(db_session)
        ticket = await service.create_ticket(
            workspace_id=owner_workspace,
            agent_id=agent_id,
            subject="Billing question",
            body="Was I charged twice?",
            created_by_user_id=user_id,
            idempotency_key=None,
        )

        stranger_view = await service.get_ticket(
            workspace_id=stranger_workspace, ticket_id=ticket.id
        )
        owner_view = await service.get_ticket(workspace_id=owner_workspace, ticket_id=ticket.id)
        assert stranger_view is None
        assert owner_view is not None
        assert (
            await service.list_tickets(workspace_id=stranger_workspace, limit=10, cursor=None)
            == []
        )
        await db_session.rollback()


class TestTriageResolution:
    async def test_a_completed_run_resolves_the_triage_fields(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        user_id = await _user(db_session)
        agent_id = await _runnable_agent(db_session, workspace_id, user_id)
        service = _service(db_session)
        ticket = await service.create_ticket(
            workspace_id=workspace_id,
            agent_id=agent_id,
            subject="Refund request",
            body="I want a refund.",
            created_by_user_id=user_id,
            idempotency_key=None,
        )
        run_repo = SqlAgentRunRepository(db_session)
        assert ticket.triage_run_id is not None
        await run_repo.append_step(
            AgentRunStep(
                id=str(uuid.uuid4()),
                run_id=ticket.triage_run_id,
                workspace_id=workspace_id,
                step_type="llm_call",
                sequence=1,
                payload={
                    "text": (
                        "category: billing\nseverity: high\nconfidence: high\n"
                        "draft_reply: We'll process your refund within 3 business days."
                    )
                },
                cost_micro_usd=None,
                created_at=datetime.now(UTC),
            )
        )
        await run_repo.update_status(run_id=ticket.triage_run_id, status=RunStatus.SUCCESS)

        resolved = await service.get_ticket(workspace_id=workspace_id, ticket_id=ticket.id)

        assert resolved is not None
        assert resolved.status is TicketStatus.TRIAGED
        assert resolved.category == "billing"
        assert resolved.priority == "high"
        assert resolved.draft_reply == "We'll process your refund within 3 business days."
        await db_session.rollback()

    async def test_a_failed_run_marks_the_ticket_failed(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        user_id = await _user(db_session)
        agent_id = await _runnable_agent(db_session, workspace_id, user_id)
        service = _service(db_session)
        ticket = await service.create_ticket(
            workspace_id=workspace_id,
            agent_id=agent_id,
            subject="Something broke",
            body="Not sure what happened.",
            created_by_user_id=user_id,
            idempotency_key=None,
        )
        run_repo = SqlAgentRunRepository(db_session)
        assert ticket.triage_run_id is not None
        await run_repo.update_status(
            run_id=ticket.triage_run_id,
            status=RunStatus.ERROR,
            error_message="provider_unavailable",
        )

        resolved = await service.get_ticket(workspace_id=workspace_id, ticket_id=ticket.id)

        assert resolved is not None
        assert resolved.status is TicketStatus.FAILED
        await db_session.rollback()

    async def test_a_still_running_run_leaves_the_ticket_in_triaging(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        user_id = await _user(db_session)
        agent_id = await _runnable_agent(db_session, workspace_id, user_id)
        service = _service(db_session)
        ticket = await service.create_ticket(
            workspace_id=workspace_id,
            agent_id=agent_id,
            subject="Still going",
            body="Just submitted this.",
            created_by_user_id=user_id,
            idempotency_key=None,
        )

        resolved = await service.get_ticket(workspace_id=workspace_id, ticket_id=ticket.id)

        assert resolved is not None
        assert resolved.status is TicketStatus.TRIAGING
        await db_session.rollback()


class TestResolve:
    async def test_resolving_a_ticket_sets_its_status(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        user_id = await _user(db_session)
        agent_id = await _runnable_agent(db_session, workspace_id, user_id)
        service = _service(db_session)
        ticket = await service.create_ticket(
            workspace_id=workspace_id,
            agent_id=agent_id,
            subject="Closing this",
            body="Handled outside the ticket.",
            created_by_user_id=user_id,
            idempotency_key=None,
        )

        resolved = await service.resolve_ticket(workspace_id=workspace_id, ticket_id=ticket.id)

        assert resolved is not None
        assert resolved.status is TicketStatus.RESOLVED
        await db_session.rollback()


class TestCreateTicketDirect:
    """Phase 13's tool-originated path — no triage sub-run, no agent
    required, classified synchronously by the caller.
    """

    async def test_creates_an_already_triaged_ticket_with_no_run(
        self, db_session: AsyncSession
    ) -> None:
        workspace_id = await _workspace(db_session)
        user_id = await _user(db_session)
        service = _service(db_session)

        ticket = await service.create_ticket_direct(
            workspace_id=workspace_id,
            subject="Product arrived damaged",
            body="The box was crushed and the item inside is broken.",
            created_by_user_id=user_id,
            category="damaged-item",
            priority="high",
        )

        assert ticket.status is TicketStatus.TRIAGED
        assert ticket.triage_run_id is None
        assert ticket.category == "damaged-item"
        assert ticket.priority == "high"
        stored = await service.get_ticket(workspace_id=workspace_id, ticket_id=ticket.id)
        assert stored is not None
        assert stored.status is TicketStatus.TRIAGED
        await db_session.rollback()

    async def test_category_and_priority_are_optional(self, db_session: AsyncSession) -> None:
        workspace_id = await _workspace(db_session)
        user_id = await _user(db_session)
        service = _service(db_session)

        ticket = await service.create_ticket_direct(
            workspace_id=workspace_id,
            subject="General question",
            body="Just asking something.",
            created_by_user_id=user_id,
        )

        assert ticket.status is TicketStatus.TRIAGED
        assert ticket.category is None
        assert ticket.priority is None
        await db_session.rollback()

    async def test_is_invisible_to_another_workspace(self, db_session: AsyncSession) -> None:
        owner_workspace = await _workspace(db_session)
        stranger_workspace = await _workspace(db_session)
        user_id = await _user(db_session)
        service = _service(db_session)

        ticket = await service.create_ticket_direct(
            workspace_id=owner_workspace,
            subject="Escalation: refund dispute",
            body="Customer disputes the refund decision.",
            created_by_user_id=user_id,
            category="escalation",
            priority="urgent",
        )

        stranger_view = await service.get_ticket(
            workspace_id=stranger_workspace, ticket_id=ticket.id
        )
        owner_view = await service.get_ticket(workspace_id=owner_workspace, ticket_id=ticket.id)
        assert stranger_view is None
        assert owner_view is not None
        await db_session.rollback()
