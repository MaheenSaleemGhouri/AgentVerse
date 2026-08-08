"""SQLAlchemy implementation of `AssistantSessionRepository`."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from agentverse_api.assistant_service.domain.entities import (
    AssistantMessage,
    AssistantRole,
    AssistantSession,
)
from agentverse_api.assistant_service.infrastructure.models import (
    AssistantMessageModel,
    AssistantSessionModel,
)


def _to_session(row: AssistantSessionModel) -> AssistantSession:
    return AssistantSession(
        id=row.id,
        workspace_id=row.workspace_id,
        user_id=row.user_id,
        title=row.title,
        created_at=row.created_at,
        last_message_at=row.last_message_at,
    )


def _to_message(row: AssistantMessageModel) -> AssistantMessage:
    # `role` is TEXT + CHECK in the schema and a Literal in the domain.
    # The cast is safe because the constraint is the enforcement point;
    # widening the domain type to `str` instead would push the check into
    # every consumer.
    role: AssistantRole = "assistant" if row.role == "assistant" else "user"
    return AssistantMessage(
        id=row.id,
        session_id=row.session_id,
        role=role,
        content=row.content,
        created_at=row.created_at,
    )


class SqlAssistantSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_session(
        self, *, workspace_id: str, user_id: str, title: str
    ) -> AssistantSession:
        row = AssistantSessionModel(workspace_id=workspace_id, user_id=user_id, title=title)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_session(row)

    async def get_session(
        self, *, workspace_id: str, user_id: str, session_id: str
    ) -> AssistantSession | None:
        row = await self._session.scalar(
            select(AssistantSessionModel).where(
                AssistantSessionModel.id == session_id,
                AssistantSessionModel.workspace_id == workspace_id,
                AssistantSessionModel.user_id == user_id,
            )
        )
        return None if row is None else _to_session(row)

    async def list_sessions(
        self, *, workspace_id: str, user_id: str, limit: int
    ) -> list[AssistantSession]:
        rows = await self._session.scalars(
            select(AssistantSessionModel)
            .where(
                AssistantSessionModel.workspace_id == workspace_id,
                AssistantSessionModel.user_id == user_id,
            )
            .order_by(AssistantSessionModel.last_message_at.desc())
            .limit(limit)
        )
        return [_to_session(row) for row in rows]

    async def list_messages(self, *, session_id: str) -> list[AssistantMessage]:
        rows = await self._session.scalars(
            select(AssistantMessageModel)
            .where(AssistantMessageModel.session_id == session_id)
            .order_by(AssistantMessageModel.seq)
        )
        return [_to_message(row) for row in rows]

    async def append_message(
        self, *, session_id: str, role: AssistantRole, content: str
    ) -> AssistantMessage:
        row = AssistantMessageModel(session_id=session_id, role=role, content=content)
        self._session.add(row)
        # The session's ordering key moves with its last turn, so the
        # sidebar's "most recent" is the conversation you were actually
        # just in, not the one you happened to open first.
        await self._session.execute(
            update(AssistantSessionModel)
            .where(AssistantSessionModel.id == session_id)
            .values(last_message_at=func.now())
        )
        await self._session.flush()
        await self._session.refresh(row)
        return _to_message(row)
