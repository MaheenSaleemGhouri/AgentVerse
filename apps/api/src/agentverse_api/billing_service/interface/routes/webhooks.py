"""`POST /api/v1/billing/webhooks/stripe`.

**Unauthenticated by design, and that is not a gap.** The provider cannot
present a session cookie or a workspace-scoped API key. Authentication
here is the HMAC signature over the raw request body, verified against a
secret only this service and the provider hold — which is a stronger
assertion than a bearer token, because it also proves the *body* was not
altered.

Three properties this handler is built around:

**The raw body, never a re-serialization.** FastAPI would happily parse
the JSON into a model first, but the signature was computed over the
exact bytes the provider sent; round-tripping through JSON can reorder
keys and renormalize numbers, and verifying the result verifies nothing.
So this reads `await request.body()` and hands those bytes to the
verifier before anything parses them.

**Nothing is trusted before verification.** The payload is not parsed,
logged, or inspected until the signature checks out. An unverified body
is attacker-controlled input, and treating it as a Stripe event even for
logging gives a forger a write into this system's logs.

**2xx means "stop retrying", not "everything was fine".** A duplicate
delivery and an event this system does not act on both return 200:
answering non-2xx would make the provider redeliver an event that was
handled correctly, compounding load during an incident. A genuine
processing failure does return 5xx, because there the retry is wanted.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from agentverse_api.billing_service.application.webhook_service import (
    WebhookOutcome,
    WebhookService,
)
from agentverse_api.billing_service.domain.payment_provider import (
    PaymentProviderPort,
    WebhookVerificationError,
)
from agentverse_api.billing_service.interface.dependencies.services import (
    get_payment_provider,
    get_webhook_service,
)
from agentverse_api.billing_service.interface.schemas.billing_actions import WebhookAckResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/billing/webhooks", tags=["billing-webhooks"])

#: Bodies larger than this are rejected before verification. Real events
#: are a few kilobytes; the cap stops an unauthenticated endpoint from
#: being used to make this service buffer arbitrary data, and costs
#: nothing since the limit is far above any legitimate payload.
_MAX_WEBHOOK_BYTES = 1024 * 1024


@router.post("/stripe", response_model=WebhookAckResponse)
async def stripe_webhook_route(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    provider: PaymentProviderPort = Depends(get_payment_provider),
    service: WebhookService = Depends(get_webhook_service),
) -> WebhookAckResponse:
    if stripe_signature is None:
        # 400, not 401: a missing signature means this is not a provider
        # request at all, and there is no credential the caller could
        # supply to make it one.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing signature header"
        )
    payload = await request.body()
    if len(payload) > _MAX_WEBHOOK_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Webhook payload too large",
        )

    try:
        event = provider.verify_webhook(payload=payload, signature=stripe_signature)
    except WebhookVerificationError as exc:
        # Logged without the payload and without the reason: the body is
        # unverified attacker-controlled input, and telling a forger
        # which check failed helps them iterate.
        logger.warning("billing_webhook_rejected")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature"
        ) from exc

    if event is None:
        # Verified, but a type this system does not act on. 200 so the
        # provider stops — every new event type the provider ships would
        # otherwise read as an outage here.
        return WebhookAckResponse(outcome=WebhookOutcome.IGNORED.value)

    outcome = await service.handle(event)
    return WebhookAckResponse(outcome=outcome.value)
