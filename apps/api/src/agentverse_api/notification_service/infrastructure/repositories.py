"""Postgres adapters for the notification context."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.notification_service.domain.notification import (
    Notification,
    NotificationKind,
    Severity,
)
from agentverse_api.notification_service.infrastructure.models import (
    NotificationDeliveryModel,
    NotificationModel,
)


def _to_notification(row: NotificationModel) -> Notification:
    return Notification(
        id=row.id,
        workspace_id=row.workspace_id,
        kind=NotificationKind(row.kind),
        severity=Severity(row.severity),
        title=row.title,
        body=row.body,
        action_path=row.action_path,
        read_at=row.read_at,
        created_at=row.created_at,
        metadata=row.notification_metadata or {},
    )


class SqlNotificationRepository:
    """Implements `domain.ports.NotificationRepository`.

    Every read filters on `workspace_id` (Rule 11), including the ones
    that also carry a notification id — an id alone would let a caller
    read or mark another tenant's notification by guessing.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        workspace_id: str,
        kind: NotificationKind,
        severity: Severity,
        title: str,
        body: str,
        action_path: str | None,
        dedupe_key: str,
        metadata: dict[str, object],
    ) -> Notification | None:
        # ON CONFLICT DO NOTHING, not a read-then-write: a dunning sweep
        # and a webhook can raise the same notification concurrently, and
        # the read-then-write version lets both pass the check.
        stmt = (
            pg_insert(NotificationModel)
            .values(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                kind=kind.value,
                severity=severity.value,
                title=title,
                body=body,
                action_path=action_path,
                dedupe_key=dedupe_key,
                notification_metadata=metadata,
            )
            .on_conflict_do_nothing(index_elements=[NotificationModel.dedupe_key])
            .returning(NotificationModel)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        # `None` is the normal outcome of a retry, not an error — see the
        # port's docstring.
        return None if row is None else _to_notification(row)

    async def list_for_workspace(
        self, *, workspace_id: str, limit: int, unread_only: bool
    ) -> list[Notification]:
        stmt = select(NotificationModel).where(NotificationModel.workspace_id == workspace_id)
        if unread_only:
            stmt = stmt.where(NotificationModel.read_at.is_(None))
        stmt = stmt.order_by(NotificationModel.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return [_to_notification(row) for row in result.scalars().all()]

    async def unread_count(self, workspace_id: str) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(NotificationModel)
            .where(
                NotificationModel.workspace_id == workspace_id,
                NotificationModel.read_at.is_(None),
            )
        )
        return int(result.scalar_one())

    async def mark_read(self, *, workspace_id: str, notification_id: str) -> bool:
        result = await self._session.execute(
            update(NotificationModel)
            .where(
                NotificationModel.id == notification_id,
                # Both predicates, always: an id-only update would let a
                # caller mark another tenant's notification read, and the
                # zero-rows result would look identical to "not found".
                NotificationModel.workspace_id == workspace_id,
                NotificationModel.read_at.is_(None),
            )
            .values(read_at=func.now())
            # `RETURNING` rather than `rowcount`: SQLAlchemy's async
            # `Result` does not expose a row count for an UPDATE, and
            # the returned ids are what the caller actually needs to
            # know — whether anything matched.
            .returning(NotificationModel.id)
        )
        return result.scalar_one_or_none() is not None

    async def mark_all_read(self, workspace_id: str) -> int:
        result = await self._session.execute(
            update(NotificationModel)
            .where(
                NotificationModel.workspace_id == workspace_id,
                NotificationModel.read_at.is_(None),
            )
            .values(read_at=func.now())
            .returning(NotificationModel.id)
        )
        return len(result.scalars().all())


class SqlDeliveryRepository:
    """Implements `domain.ports.DeliveryRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(self, *, notification_id: str, address: str) -> str | None:
        delivery_id = str(uuid.uuid4())
        stmt = (
            pg_insert(NotificationDeliveryModel)
            .values(
                id=delivery_id,
                notification_id=notification_id,
                channel="email",
                address=address,
                status="pending",
            )
            .on_conflict_do_nothing(
                index_elements=[
                    NotificationDeliveryModel.notification_id,
                    NotificationDeliveryModel.channel,
                ]
            )
            .returning(NotificationDeliveryModel.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def record_result(
        self, *, delivery_id: str, provider_message_id: str | None, error: str | None
    ) -> None:
        await self._session.execute(
            update(NotificationDeliveryModel)
            .where(NotificationDeliveryModel.id == delivery_id)
            .values(
                status="failed" if error else "sent",
                provider_message_id=provider_message_id,
                error=error,
                completed_at=datetime.now(UTC),
            )
        )
