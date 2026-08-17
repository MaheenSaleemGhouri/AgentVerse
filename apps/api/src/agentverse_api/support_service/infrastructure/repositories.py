"""Postgres adapter for `domain.ports.SupportTicketRepository`."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.support_service.domain.entities import SupportTicket, TicketStatus
from agentverse_api.support_service.infrastructure.models import SupportTicketModel


class SqlSupportTicketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        workspace_id: str,
        subject: str,
        body: str,
        triage_run_id: str | None,
        created_by_user_id: str,
    ) -> SupportTicket:
        row = SupportTicketModel(
            workspace_id=workspace_id,
            subject=subject,
            body=body,
            status=TicketStatus.TRIAGING.value,
            triage_run_id=triage_run_id,
            created_by_user_id=created_by_user_id,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_ticket(row)

    async def get(self, *, workspace_id: str, ticket_id: str) -> SupportTicket | None:
        result = await self._session.execute(
            select(SupportTicketModel).where(
                SupportTicketModel.id == ticket_id,
                SupportTicketModel.workspace_id == workspace_id,
            )
        )
        row = result.scalar_one_or_none()
        return None if row is None else _to_ticket(row)

    async def list_for_workspace(
        self, *, workspace_id: str, limit: int, cursor: str | None
    ) -> list[SupportTicket]:
        statement = select(SupportTicketModel).where(
            SupportTicketModel.workspace_id == workspace_id
        )
        if cursor:
            # Keyset on created_at, matching this repo's other
            # fast-appending, workspace-scoped log tables (CLAUDE.md §7).
            statement = statement.where(
                SupportTicketModel.created_at < datetime.fromisoformat(cursor)
            )
        result = await self._session.execute(
            statement.order_by(SupportTicketModel.created_at.desc()).limit(limit)
        )
        return [_to_ticket(row) for row in result.scalars()]

    async def update_triage_result(
        self,
        *,
        ticket_id: str,
        status: TicketStatus,
        category: str | None = None,
        priority: str | None = None,
        confidence: str | None = None,
        draft_reply: str | None = None,
    ) -> SupportTicket:
        result = await self._session.execute(
            select(SupportTicketModel).where(SupportTicketModel.id == ticket_id)
        )
        row = result.scalar_one()
        row.status = status.value
        row.category = category
        row.priority = priority
        row.confidence = confidence
        row.draft_reply = draft_reply
        row.updated_at = datetime.now(UTC)
        await self._session.flush()
        return _to_ticket(row)

    async def set_status(self, *, ticket_id: str, status: TicketStatus) -> SupportTicket:
        result = await self._session.execute(
            select(SupportTicketModel).where(SupportTicketModel.id == ticket_id)
        )
        row = result.scalar_one()
        row.status = status.value
        row.updated_at = datetime.now(UTC)
        await self._session.flush()
        return _to_ticket(row)


def _to_ticket(row: SupportTicketModel) -> SupportTicket:
    return SupportTicket(
        id=row.id,
        workspace_id=row.workspace_id,
        subject=row.subject,
        body=row.body,
        status=TicketStatus(row.status),
        category=row.category,
        priority=row.priority,
        confidence=row.confidence,
        draft_reply=row.draft_reply,
        triage_run_id=row.triage_run_id,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
