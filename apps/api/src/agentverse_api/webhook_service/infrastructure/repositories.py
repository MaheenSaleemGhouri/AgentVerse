"""Postgres adapters for the webhook context."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from agentverse_shared.security.envelope import CredentialVault
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.webhook_service.domain.endpoint import WebhookEndpoint, WebhookEvent
from agentverse_api.webhook_service.domain.ports import DeliveryRecord
from agentverse_api.webhook_service.infrastructure.models import (
    WebhookDeliveryModel,
    WebhookEndpointModel,
)


def _to_endpoint(row: WebhookEndpointModel) -> WebhookEndpoint:
    return WebhookEndpoint(
        id=row.id,
        workspace_id=row.workspace_id,
        url=row.url,
        description=row.description,
        # Unknown stored values are dropped rather than raising: an event
        # type removed in a later release would otherwise make every
        # endpoint that once subscribed to it unreadable, including for
        # the customer trying to remove it.
        events=frozenset(
            WebhookEvent(name) for name in row.events if name in {e.value for e in WebhookEvent}
        ),
        is_active=row.is_active,
        consecutive_failures=row.consecutive_failures,
        disabled_at=row.disabled_at,
        disabled_reason=row.disabled_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _associated_data(workspace_id: str, endpoint_id: str) -> bytes:
    """Binds the sealed secret to the row it belongs to.

    Authenticated but not encrypted, so ciphertext copied into a
    different endpoint's row fails to decrypt rather than silently
    becoming that endpoint's secret.
    """
    return f"webhook:{workspace_id}:{endpoint_id}".encode()


class SqlEndpointRepository:
    """Implements `domain.ports.EndpointRepository`."""

    def __init__(self, session: AsyncSession, vault: CredentialVault) -> None:
        self._session = session
        self._vault = vault

    async def get(self, *, workspace_id: str, endpoint_id: str) -> WebhookEndpoint | None:
        result = await self._session.execute(
            select(WebhookEndpointModel).where(
                WebhookEndpointModel.id == endpoint_id,
                WebhookEndpointModel.workspace_id == workspace_id,
            )
        )
        row = result.scalar_one_or_none()
        return None if row is None else _to_endpoint(row)

    async def list_for_workspace(self, *, workspace_id: str) -> list[WebhookEndpoint]:
        result = await self._session.execute(
            select(WebhookEndpointModel)
            .where(WebhookEndpointModel.workspace_id == workspace_id)
            .order_by(WebhookEndpointModel.created_at.desc())
        )
        return [_to_endpoint(row) for row in result.scalars().all()]

    async def list_subscribed(
        self, *, workspace_id: str, event: WebhookEvent
    ) -> list[WebhookEndpoint]:
        # Filtered in SQL with the array containment operator: dispatch
        # runs on the completion path of every agent run, and loading
        # fifty endpoints to find the two that care would put that cost
        # on every run.
        result = await self._session.execute(
            select(WebhookEndpointModel).where(
                WebhookEndpointModel.workspace_id == workspace_id,
                WebhookEndpointModel.is_active.is_(True),
                WebhookEndpointModel.events.contains([event.value]),
            )
        )
        return [_to_endpoint(row) for row in result.scalars().all()]

    async def create(
        self,
        *,
        workspace_id: str,
        url: str,
        description: str,
        events: frozenset[WebhookEvent],
        secret: str,
    ) -> WebhookEndpoint:
        endpoint_id = str(uuid.uuid4())
        sealed = self._vault.seal(
            secret, associated_data=_associated_data(workspace_id, endpoint_id)
        )
        row = WebhookEndpointModel(
            id=endpoint_id,
            workspace_id=workspace_id,
            url=url,
            description=description,
            # Sorted so two endpoints with the same subscriptions store
            # them identically — otherwise a diff of two rows shows a
            # change that is only ordering.
            events=sorted(event.value for event in events),
            secret_ciphertext=sealed.ciphertext,
            wrapped_dek=sealed.wrapped_dek,
            key_version=sealed.key_version,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_endpoint(row)

    async def update(
        self,
        *,
        workspace_id: str,
        endpoint_id: str,
        url: str | None,
        description: str | None,
        events: frozenset[WebhookEvent] | None,
        is_active: bool | None,
        reset_failures: bool,
    ) -> WebhookEndpoint:
        result = await self._session.execute(
            select(WebhookEndpointModel).where(
                WebhookEndpointModel.id == endpoint_id,
                WebhookEndpointModel.workspace_id == workspace_id,
            )
        )
        row = result.scalar_one()
        if url is not None:
            row.url = url
        if description is not None:
            row.description = description
        if events is not None:
            row.events = sorted(event.value for event in events)
        if is_active is not None:
            row.is_active = is_active
        if reset_failures:
            row.consecutive_failures = 0
            row.disabled_at = None
            row.disabled_reason = None
        await self._session.flush()
        await self._session.refresh(row)
        return _to_endpoint(row)

    async def replace_secret(self, *, workspace_id: str, endpoint_id: str, secret: str) -> None:
        result = await self._session.execute(
            select(WebhookEndpointModel).where(
                WebhookEndpointModel.id == endpoint_id,
                WebhookEndpointModel.workspace_id == workspace_id,
            )
        )
        row = result.scalar_one()
        sealed = self._vault.seal(
            secret, associated_data=_associated_data(workspace_id, endpoint_id)
        )
        row.secret_ciphertext = sealed.ciphertext
        row.wrapped_dek = sealed.wrapped_dek
        row.key_version = sealed.key_version
        await self._session.flush()

    async def delete(self, *, workspace_id: str, endpoint_id: str) -> None:
        await self._session.execute(
            sql_delete(WebhookEndpointModel).where(
                WebhookEndpointModel.id == endpoint_id,
                WebhookEndpointModel.workspace_id == workspace_id,
            )
        )


def _to_record(row: WebhookDeliveryModel) -> DeliveryRecord:
    return DeliveryRecord(
        id=row.id,
        endpoint_id=row.endpoint_id,
        event_type=row.event_type,
        status=row.status,
        attempts=row.attempts,
        last_response_status=row.last_response_status,
        last_error=row.last_error,
        next_attempt_at=row.next_attempt_at,
        delivered_at=row.delivered_at,
        created_at=row.created_at,
    )


class SqlDeliveryRepository:
    """Implements `domain.ports.DeliveryRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(
        self,
        *,
        workspace_id: str,
        endpoint_id: str,
        event_type: str,
        event_id: str,
        payload: dict[str, object],
    ) -> bool:
        # `ON CONFLICT DO NOTHING` against the unique
        # `(endpoint_id, event_id)` index rather than a check-then-insert:
        # two concurrent dispatches of the same event would both pass a
        # check, and the customer would receive it twice.
        result = await self._session.execute(
            pg_insert(WebhookDeliveryModel)
            .values(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                endpoint_id=endpoint_id,
                event_type=event_type,
                event_id=event_id,
                payload=payload,
                status="pending",
                next_attempt_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(
                index_elements=[
                    WebhookDeliveryModel.endpoint_id,
                    WebhookDeliveryModel.event_id,
                ]
            )
            .returning(WebhookDeliveryModel.id)
        )
        return result.scalar_one_or_none() is not None

    async def list_for_workspace(
        self, *, workspace_id: str, endpoint_id: str | None, limit: int
    ) -> list[DeliveryRecord]:
        stmt = select(WebhookDeliveryModel).where(WebhookDeliveryModel.workspace_id == workspace_id)
        if endpoint_id is not None:
            stmt = stmt.where(WebhookDeliveryModel.endpoint_id == endpoint_id)
        result = await self._session.execute(
            stmt.order_by(WebhookDeliveryModel.created_at.desc()).limit(limit)
        )
        return [_to_record(row) for row in result.scalars().all()]
