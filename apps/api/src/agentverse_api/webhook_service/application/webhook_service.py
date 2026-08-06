"""Managing webhook endpoints, and enqueuing deliveries.

**Delivery does not happen here.** This service writes a `pending` row
and returns; the worker drains it. A POST to a customer's endpoint is an
unbounded wait on a third party, and doing it inline would mean an agent
run's completion latency depends on whether someone's server is up
(Rule 14).

**A URL is validated before it is stored, not only before it is called.**
The customer supplies it, so it is an SSRF primitive: `http://10.0.0.5`
or the cloud metadata address would otherwise turn the platform into a
proxy into its own network. `egress_guard` is the same one agent tool
calls go through (Rule 6) — validating at write time means the customer
hears about it while they are looking at the form, and validating again
at delivery time means a hostname that later resolves somewhere private
is still refused.

**The secret is shown once, in full, at creation.** Afterwards it can be
rotated but not re-read through the API — the same discipline API keys
follow. It is *stored* decryptably because the customer's verifier needs
it; that is a different question from whether the API hands it back on
demand.
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from agentverse_shared.security.egress_guard import EgressDeniedError, validate_destination

from agentverse_api.webhook_service.domain.endpoint import (
    WebhookEndpoint,
    WebhookEvent,
    parse_events,
)
from agentverse_api.webhook_service.domain.ports import (
    DeliveryRecord,
    DeliveryRepository,
    EndpointRepository,
)


class EndpointNotFoundError(Exception):
    """Maps to HTTP 404.

    Also raised for an endpoint in another workspace — the repository
    queries are workspace-scoped, so a cross-tenant id is indistinguishable
    from a missing one, which is the point (Rule 11).
    """

    def __init__(self, endpoint_id: str) -> None:
        self.endpoint_id = endpoint_id
        super().__init__("No such webhook endpoint")


class UnsafeWebhookUrlError(Exception):
    """The URL points somewhere the platform will not call. Maps to 422.

    Carries the reason: a customer told "invalid URL" when they typed a
    private address will retype the same address.
    """

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"This URL cannot receive webhooks: {reason}")


#: Long enough that guessing is hopeless, short enough to paste. 32 bytes
#: of urandom, hex-encoded — the same shape as the API key secret, so
#: customers see one convention.
_SECRET_BYTES = 32
_SECRET_PREFIX = "whsec_"


def generate_secret() -> str:
    return f"{_SECRET_PREFIX}{secrets.token_hex(_SECRET_BYTES)}"


@dataclass(frozen=True, slots=True)
class CreatedEndpoint:
    """The endpoint plus its secret, which is returned exactly once."""

    endpoint: WebhookEndpoint
    secret: str


@dataclass(slots=True)
class WebhookService:
    endpoints: EndpointRepository
    deliveries: DeliveryRepository

    # ---- endpoint management -----------------------------------------

    async def create_endpoint(
        self, *, workspace_id: str, url: str, description: str, events: list[str]
    ) -> CreatedEndpoint:
        parsed = parse_events(events)
        await self._assert_safe(url)
        secret = generate_secret()
        endpoint = await self.endpoints.create(
            workspace_id=workspace_id,
            url=url,
            description=description,
            events=parsed,
            secret=secret,
        )
        return CreatedEndpoint(endpoint=endpoint, secret=secret)

    async def list_endpoints(self, *, workspace_id: str) -> list[WebhookEndpoint]:
        return await self.endpoints.list_for_workspace(workspace_id=workspace_id)

    async def update_endpoint(
        self,
        *,
        workspace_id: str,
        endpoint_id: str,
        url: str | None = None,
        description: str | None = None,
        events: list[str] | None = None,
        is_active: bool | None = None,
    ) -> WebhookEndpoint:
        await self._require(workspace_id=workspace_id, endpoint_id=endpoint_id)
        if url is not None:
            await self._assert_safe(url)
        parsed = parse_events(events) if events is not None else None
        return await self.endpoints.update(
            workspace_id=workspace_id,
            endpoint_id=endpoint_id,
            url=url,
            description=description,
            events=parsed,
            is_active=is_active,
            # Re-enabling clears the failure counter. Without this an
            # endpoint disabled by 20 failures would be switched back on
            # and disabled again by its 21st, which reads as the toggle
            # being broken.
            reset_failures=is_active is True,
        )

    async def rotate_secret(self, *, workspace_id: str, endpoint_id: str) -> str:
        """A new secret, returned once.

        The old one stops working immediately rather than overlapping.
        An overlap window is the right answer for a busy integration, and
        it needs a second stored secret and an expiry — real scope, not a
        line of code, and nobody has asked for it yet.
        """
        await self._require(workspace_id=workspace_id, endpoint_id=endpoint_id)
        secret = generate_secret()
        await self.endpoints.replace_secret(
            workspace_id=workspace_id, endpoint_id=endpoint_id, secret=secret
        )
        return secret

    async def delete_endpoint(self, *, workspace_id: str, endpoint_id: str) -> None:
        await self._require(workspace_id=workspace_id, endpoint_id=endpoint_id)
        await self.endpoints.delete(workspace_id=workspace_id, endpoint_id=endpoint_id)

    # ---- dispatch ----------------------------------------------------

    async def dispatch(
        self,
        *,
        workspace_id: str,
        event: WebhookEvent,
        event_id: str,
        payload: dict[str, object],
    ) -> int:
        """Queue this event for every endpoint that wants it.

        Returns how many deliveries were queued, so a caller can tell
        "nobody subscribed" from "queued" without a second query.

        `event_id` must be derived from the row that caused the event —
        a run id, a listing id — never generated here. That is what makes
        a redelivered dispatch idempotent: the unique index on
        `(endpoint_id, event_id)` absorbs the second one instead of
        sending the customer a duplicate.
        """
        subscribers = await self.endpoints.list_subscribed(workspace_id=workspace_id, event=event)
        queued = 0
        for endpoint in subscribers:
            created = await self.deliveries.enqueue(
                workspace_id=workspace_id,
                endpoint_id=endpoint.id,
                event_type=event.value,
                event_id=event_id,
                payload=self._envelope(event=event, event_id=event_id, payload=payload),
            )
            queued += int(created)
        return queued

    def _envelope(
        self, *, event: WebhookEvent, event_id: str, payload: dict[str, object]
    ) -> dict[str, object]:
        """The body a customer actually receives.

        Wrapped rather than sent raw so every event has the same outer
        shape — a receiver can route on `type` and dedupe on `id` without
        knowing which event it is. `api_version` is here from the start
        because adding it later would itself be the breaking change it
        exists to prevent.
        """
        return {
            "id": f"evt_{uuid.uuid5(uuid.NAMESPACE_URL, f'{event.value}:{event_id}').hex}",
            "type": event.value,
            "api_version": "v1",
            "created_at": datetime.now(UTC).isoformat(),
            "data": payload,
        }

    async def list_deliveries(
        self, *, workspace_id: str, endpoint_id: str | None = None, limit: int = 50
    ) -> list[DeliveryRecord]:
        """Recent attempts, so a customer can debug their own endpoint
        without asking support what we sent them.
        """
        return await self.deliveries.list_for_workspace(
            workspace_id=workspace_id, endpoint_id=endpoint_id, limit=min(max(limit, 1), 200)
        )

    # ---- helpers -----------------------------------------------------

    async def _assert_safe(self, url: str) -> None:
        try:
            await validate_destination(url)
        except EgressDeniedError as exc:
            raise UnsafeWebhookUrlError(url, str(exc)) from exc

    async def _require(self, *, workspace_id: str, endpoint_id: str) -> WebhookEndpoint:
        endpoint = await self.endpoints.get(workspace_id=workspace_id, endpoint_id=endpoint_id)
        if endpoint is None:
            raise EndpointNotFoundError(endpoint_id)
        return endpoint


def serialize_body(envelope: dict[str, object]) -> str:
    """The exact bytes that get signed and sent.

    One function, because the signature covers the body: signing a
    differently-serialized string than the one transmitted produces a
    signature that fails at every customer, and the bug is invisible on
    our side. `sort_keys` and no spaces make it byte-stable across
    processes.
    """
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"), default=str)
