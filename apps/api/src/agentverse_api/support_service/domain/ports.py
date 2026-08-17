"""Ports this context depends on. `run_agent`'s own collaborator ports
(`AgentRepository`, `AgentRunRepository`, `JobQueueProducer`,
`LockFactory`) are `orchestration_service`'s, imported directly rather
than re-declared here — this context calls that context's existing use
case, it does not own or duplicate its contract.
"""

from __future__ import annotations

from typing import Protocol

from agentverse_api.support_service.domain.entities import SupportTicket, TicketStatus


class SupportTicketRepository(Protocol):
    async def create(
        self,
        *,
        workspace_id: str,
        subject: str,
        body: str,
        triage_run_id: str | None,
        created_by_user_id: str,
    ) -> SupportTicket: ...

    async def get(self, *, workspace_id: str, ticket_id: str) -> SupportTicket | None: ...

    async def list_for_workspace(
        self, *, workspace_id: str, limit: int, cursor: str | None
    ) -> list[SupportTicket]: ...

    async def update_triage_result(
        self,
        *,
        ticket_id: str,
        status: TicketStatus,
        category: str | None = None,
        priority: str | None = None,
        confidence: str | None = None,
        draft_reply: str | None = None,
    ) -> SupportTicket: ...

    async def set_status(self, *, ticket_id: str, status: TicketStatus) -> SupportTicket: ...
