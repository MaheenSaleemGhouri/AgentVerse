"""Composition root for `support_service`. Reuses
`orchestration_service`'s own composition-root factories for
`run_agent`'s collaborators — this context calls that use case, it does
not own a second copy of its wiring.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.infrastructure.db import get_db_session
from agentverse_api.orchestration_service.application.run_agent import LockFactory
from agentverse_api.orchestration_service.domain.ports.agent_repository import AgentRepository
from agentverse_api.orchestration_service.domain.ports.run_repository import AgentRunRepository
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_agent_repository,
    get_agent_run_repository,
    get_job_queue_producer,
    get_lock_factory,
)
from agentverse_api.support_service.application.support_ticket_service import (
    SupportTicketService,
)
from agentverse_api.support_service.infrastructure.repositories import SqlSupportTicketRepository


def get_support_ticket_service(
    session: AsyncSession = Depends(get_db_session),
    agent_repo: AgentRepository = Depends(get_agent_repository),
    run_repo: AgentRunRepository = Depends(get_agent_run_repository),
    producer: JobQueueProducer = Depends(get_job_queue_producer),
    lock_factory: LockFactory = Depends(get_lock_factory),
) -> SupportTicketService:
    return SupportTicketService(
        tickets=SqlSupportTicketRepository(session),
        agent_repo=agent_repo,
        run_repo=run_repo,
        producer=producer,
        lock_factory=lock_factory,
    )
