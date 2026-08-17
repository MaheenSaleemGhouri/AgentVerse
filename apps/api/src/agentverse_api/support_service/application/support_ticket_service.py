"""Creates a support ticket by triggering a real agent run through the
existing `orchestration_service.application.run_agent` use case
(CLAUDE.md §16 — "Do NOT build a separate hardcoded AI system"), and
resolves a ticket's triage result by reading that run's own recorded
steps back — the same data an SSE client watching the run would see,
just polled instead of streamed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentverse_api.orchestration_service.application.run_agent import LockFactory, run_agent
from agentverse_api.orchestration_service.domain.ports.agent_repository import AgentRepository
from agentverse_api.orchestration_service.domain.ports.run_repository import AgentRunRepository
from agentverse_api.orchestration_service.domain.run_entities import RunStatus
from agentverse_api.orchestration_service.infrastructure.queue.job_queue_producer import (
    JobQueueProducer,
)
from agentverse_api.support_service.domain.entities import SupportTicket, TicketStatus
from agentverse_api.support_service.domain.ports import SupportTicketRepository
from agentverse_api.support_service.domain.triage_parser import parse_triage_output

#: Capped for the same reason CLAUDE.md §7 caps every free-text field
#: that reaches an LLM prompt: bounding prompt-injection blast radius
#: and per-run cost, not because a real ticket is ever this long.
MAX_BODY_LENGTH = 8000


@dataclass(slots=True)
class SupportTicketService:
    tickets: SupportTicketRepository
    agent_repo: AgentRepository
    run_repo: AgentRunRepository
    producer: JobQueueProducer
    lock_factory: LockFactory

    async def create_ticket(
        self,
        *,
        workspace_id: str,
        agent_id: str,
        subject: str,
        body: str,
        created_by_user_id: str,
        idempotency_key: str | None,
    ) -> SupportTicket:
        run = await run_agent(
            workspace_id=workspace_id,
            agent_id=agent_id,
            input={"prompt": f"Subject: {subject}\n\n{body}"},
            idempotency_key=idempotency_key,
            agent_repo=self.agent_repo,
            run_repo=self.run_repo,
            producer=self.producer,
            lock_factory=self.lock_factory,
        )
        return await self.tickets.create(
            workspace_id=workspace_id,
            subject=subject,
            body=body,
            triage_run_id=run.id,
            created_by_user_id=created_by_user_id,
        )

    async def get_ticket(self, *, workspace_id: str, ticket_id: str) -> SupportTicket | None:
        """Reads the ticket, resolving its triage result from the run's
        own steps if the run has finished since it was last read —
        idempotent: a ticket already `TRIAGED`/`FAILED`/`RESOLVED` is
        returned as stored, never re-parsed.
        """
        ticket = await self.tickets.get(workspace_id=workspace_id, ticket_id=ticket_id)
        if ticket is None or ticket.status is not TicketStatus.TRIAGING:
            return ticket
        if ticket.triage_run_id is None:
            return ticket

        run = await self.run_repo.get_run(workspace_id=workspace_id, run_id=ticket.triage_run_id)
        if run is None or run.status in (RunStatus.QUEUED, RunStatus.RUNNING):
            return ticket
        if run.status in (RunStatus.ERROR, RunStatus.CANCELLED):
            return await self.tickets.update_triage_result(
                ticket_id=ticket.id, status=TicketStatus.FAILED
            )

        steps = await self.run_repo.list_steps(run_id=run.id)
        llm_steps = [step for step in steps if step.step_type == "llm_call"]
        text = _final_text(llm_steps[-1].payload) if llm_steps else ""
        fields = parse_triage_output(text)
        if not fields.is_complete:
            return await self.tickets.update_triage_result(
                ticket_id=ticket.id, status=TicketStatus.FAILED
            )
        return await self.tickets.update_triage_result(
            ticket_id=ticket.id,
            status=TicketStatus.TRIAGED,
            category=fields.category,
            priority=fields.priority,
            confidence=fields.confidence,
            draft_reply=fields.draft_reply,
        )

    async def list_tickets(
        self, *, workspace_id: str, limit: int, cursor: str | None
    ) -> list[SupportTicket]:
        return await self.tickets.list_for_workspace(
            workspace_id=workspace_id, limit=limit, cursor=cursor
        )

    async def resolve_ticket(self, *, workspace_id: str, ticket_id: str) -> SupportTicket | None:
        ticket = await self.tickets.get(workspace_id=workspace_id, ticket_id=ticket_id)
        if ticket is None:
            return None
        return await self.tickets.set_status(ticket_id=ticket.id, status=TicketStatus.RESOLVED)


def _final_text(payload: dict[str, Any]) -> str:
    text = payload.get("text")
    return text if isinstance(text, str) else ""
