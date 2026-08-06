"""`/api/v1/workspaces/{id}/webhooks` — outbound webhook endpoints.

Distinct from `billing_service`'s `/webhooks`, which receives *inbound*
calls from Stripe. These are calls the platform makes outward, to a URL
the customer supplies — which is why every one of them is validated
through the same egress guard agent tool calls use (Rule 6). A
customer-supplied URL is an SSRF primitive, and this is the surface that
would turn the platform into a proxy into its own network.

`require_admin` throughout: a webhook endpoint receives run payloads and
billing events, so subscribing one is a decision about where a
workspace's data goes.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, HttpUrl

from agentverse_api.auth_service.domain.entities import WorkspaceContext
from agentverse_api.auth_service.interface.dependencies.require_role import (
    require_admin,
    require_member,
)
from agentverse_api.webhook_service.application.webhook_service import (
    EndpointNotFoundError,
    UnsafeWebhookUrlError,
    WebhookService,
)
from agentverse_api.webhook_service.domain.endpoint import (
    InvalidEventTypeError,
    WebhookEndpoint,
    WebhookEvent,
)
from agentverse_api.webhook_service.domain.signing import (
    RECOMMENDED_TOLERANCE_SECONDS,
    SIGNATURE_VERSION,
)
from agentverse_api.webhook_service.interface.dependencies.services import get_webhook_service

router = APIRouter(prefix="/api/v1/workspaces", tags=["webhooks"])


class EndpointResponse(BaseModel):
    id: str
    url: str
    description: str
    events: list[str]
    is_active: bool
    #: Surfaced so a customer can see an endpoint is in trouble before it
    #: is switched off, rather than discovering it after.
    consecutive_failures: int
    disabled_at: datetime | None
    disabled_reason: str | None
    created_at: datetime


class CreatedEndpointResponse(EndpointResponse):
    #: Returned exactly once, at creation. Stored decryptably because the
    #: customer's verifier needs it, but never handed back by a later
    #: read — losing it means rotating, the same as an API key.
    secret: str
    #: How to verify, inline, so the integration can be written without
    #: leaving the response.
    signature_header: str = "AgentVerse-Signature"
    signature_format: str = f"t=<unix-seconds>,{SIGNATURE_VERSION}=<hex-hmac-sha256>"
    signed_payload: str = "<timestamp>.<raw-request-body>"
    recommended_tolerance_seconds: int = RECOMMENDED_TOLERANCE_SECONDS


class DeliveryResponse(BaseModel):
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


class CreateEndpointRequest(BaseModel):
    #: `HttpUrl` rejects a malformed or non-HTTP URL at the schema
    #: boundary; the egress guard then rejects one that is well-formed
    #: but points somewhere private. Two different checks, both needed.
    url: HttpUrl
    description: str = Field(default="", max_length=280)
    #: No default. An endpoint that silently subscribed to everything
    #: would receive events added in later releases, at whatever volume
    #: they arrive, without anyone choosing that.
    events: list[str] = Field(min_length=1, max_length=len(WebhookEvent))


class UpdateEndpointRequest(BaseModel):
    url: HttpUrl | None = None
    description: str | None = Field(default=None, max_length=280)
    events: list[str] | None = Field(default=None, max_length=len(WebhookEvent))
    is_active: bool | None = None


class SecretResponse(BaseModel):
    secret: str


def _to_response(endpoint: WebhookEndpoint) -> EndpointResponse:
    return EndpointResponse(
        id=endpoint.id,
        url=endpoint.url,
        description=endpoint.description,
        events=sorted(event.value for event in endpoint.events),
        is_active=endpoint.is_active,
        consecutive_failures=endpoint.consecutive_failures,
        disabled_at=endpoint.disabled_at,
        disabled_reason=endpoint.disabled_reason,
        created_at=endpoint.created_at,
    )


@router.get("/{workspace_id}/webhooks/events", response_model=list[str])
async def list_event_types_route(
    _context: WorkspaceContext = Depends(require_member),
) -> list[str]:
    """Everything that can be subscribed to.

    Served from the enum rather than documented separately, so the list
    a client sees and the list the validator accepts cannot disagree.
    """
    return sorted(event.value for event in WebhookEvent)


@router.get("/{workspace_id}/webhooks", response_model=list[EndpointResponse])
async def list_endpoints_route(
    context: WorkspaceContext = Depends(require_member),
    service: WebhookService = Depends(get_webhook_service),
) -> list[EndpointResponse]:
    endpoints = await service.list_endpoints(workspace_id=context.workspace_id)
    return [_to_response(endpoint) for endpoint in endpoints]


@router.post(
    "/{workspace_id}/webhooks",
    response_model=CreatedEndpointResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_endpoint_route(
    body: CreateEndpointRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: WebhookService = Depends(get_webhook_service),
) -> CreatedEndpointResponse:
    """Register an endpoint. The signing secret is returned once, here.

    The URL is checked against the egress guard before it is stored, not
    only before it is called — so a customer who typed a private address
    hears about it while they are looking at the form.
    """
    try:
        created = await service.create_endpoint(
            workspace_id=context.workspace_id,
            url=str(body.url),
            description=body.description,
            events=body.events,
        )
    except InvalidEventTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except UnsafeWebhookUrlError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "unsafe_webhook_url", "message": str(exc)},
        ) from exc

    base = _to_response(created.endpoint)
    return CreatedEndpointResponse(**base.model_dump(), secret=created.secret)


@router.patch("/{workspace_id}/webhooks/{endpoint_id}", response_model=EndpointResponse)
async def update_endpoint_route(
    endpoint_id: str,
    body: UpdateEndpointRequest,
    context: WorkspaceContext = Depends(require_admin),
    service: WebhookService = Depends(get_webhook_service),
) -> EndpointResponse:
    try:
        endpoint = await service.update_endpoint(
            workspace_id=context.workspace_id,
            endpoint_id=endpoint_id,
            url=str(body.url) if body.url is not None else None,
            description=body.description,
            events=body.events,
            is_active=body.is_active,
        )
    except EndpointNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such webhook endpoint"
        ) from exc
    except InvalidEventTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except UnsafeWebhookUrlError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "unsafe_webhook_url", "message": str(exc)},
        ) from exc
    return _to_response(endpoint)


@router.post("/{workspace_id}/webhooks/{endpoint_id}/rotate-secret", response_model=SecretResponse)
async def rotate_secret_route(
    endpoint_id: str,
    context: WorkspaceContext = Depends(require_admin),
    service: WebhookService = Depends(get_webhook_service),
) -> SecretResponse:
    """A new signing secret, shown once.

    The old one stops working immediately — there is no overlap window.
    That is the right behaviour for a leaked secret, which is the reason
    rotation exists, and the wrong one for a planned rotation on a busy
    integration. An overlap needs a second stored secret and an expiry;
    it is real scope, not a flag, and nobody has asked for it yet.
    """
    try:
        secret = await service.rotate_secret(
            workspace_id=context.workspace_id, endpoint_id=endpoint_id
        )
    except EndpointNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such webhook endpoint"
        ) from exc
    return SecretResponse(secret=secret)


@router.delete(
    "/{workspace_id}/webhooks/{endpoint_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_endpoint_route(
    endpoint_id: str,
    context: WorkspaceContext = Depends(require_admin),
    service: WebhookService = Depends(get_webhook_service),
) -> None:
    try:
        await service.delete_endpoint(workspace_id=context.workspace_id, endpoint_id=endpoint_id)
    except EndpointNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such webhook endpoint"
        ) from exc


@router.get("/{workspace_id}/webhooks/deliveries", response_model=list[DeliveryResponse])
async def list_deliveries_route(
    context: WorkspaceContext = Depends(require_member),
    service: WebhookService = Depends(get_webhook_service),
    endpoint_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[DeliveryResponse]:
    """Recent attempts, so a customer can debug their own endpoint
    without asking support what we sent.

    The payload is deliberately absent: this is for "did it arrive and
    what did my server say", and echoing every body would turn a list
    endpoint into a bulk export of the workspace's own run data.
    """
    records = await service.list_deliveries(
        workspace_id=context.workspace_id, endpoint_id=endpoint_id, limit=limit
    )
    return [DeliveryResponse.model_validate(record, from_attributes=True) for record in records]
