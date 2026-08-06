"""Repository ports for the webhook context.

Every method takes `workspace_id` and every query filters by it. There is
no public-catalog exception here — an endpoint URL and its delivery
history are a workspace's own operational data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from agentverse_api.webhook_service.domain.endpoint import WebhookEndpoint, WebhookEvent


@dataclass(frozen=True, slots=True)
class DeliveryRecord:
    """One delivery, as the API reports it back.

    Deliberately without the payload: a delivery list is for debugging
    "did it arrive and what did my server say", and echoing the full body
    of every attempt turns a list endpoint into a bulk data export.
    """

    id: str
    endpoint_id: str
    event_type: str
    status: str
    attempts: int
    last_response_status: int | None
    last_error: str | None
    next_attempt_at: datetime
    delivered_at: datetime | None
    created_at: datetime


class EndpointRepository(Protocol):
    async def get(self, *, workspace_id: str, endpoint_id: str) -> WebhookEndpoint | None: ...

    async def list_for_workspace(self, *, workspace_id: str) -> list[WebhookEndpoint]: ...

    async def list_subscribed(
        self, *, workspace_id: str, event: WebhookEvent
    ) -> list[WebhookEndpoint]:
        """Active endpoints in this workspace subscribed to `event`.

        Filtered in SQL rather than by loading every endpoint and testing
        in Python: dispatch runs on the completion path of every agent
        run, and a workspace with fifty endpoints should not cost fifty
        rows to find the two that care.
        """
        ...

    async def create(
        self,
        *,
        workspace_id: str,
        url: str,
        description: str,
        events: frozenset[WebhookEvent],
        secret: str,
    ) -> WebhookEndpoint: ...

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
    ) -> WebhookEndpoint: ...

    async def replace_secret(self, *, workspace_id: str, endpoint_id: str, secret: str) -> None: ...

    async def delete(self, *, workspace_id: str, endpoint_id: str) -> None: ...


class DeliveryRepository(Protocol):
    async def enqueue(
        self,
        *,
        workspace_id: str,
        endpoint_id: str,
        event_type: str,
        event_id: str,
        payload: dict[str, object],
    ) -> bool:
        """Queue one delivery. `False` if this event was already queued.

        Absorbed by the unique index on `(endpoint_id, event_id)` rather
        than by a check-then-insert, because two concurrent dispatches of
        the same event would both pass a check and the customer would
        receive it twice.
        """
        ...

    async def list_for_workspace(
        self, *, workspace_id: str, endpoint_id: str | None, limit: int
    ) -> list[DeliveryRecord]: ...
