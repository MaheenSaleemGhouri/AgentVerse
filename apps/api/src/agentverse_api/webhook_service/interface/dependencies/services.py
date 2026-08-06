"""Composition root for the webhook context."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.infrastructure.db import get_db_session
from agentverse_api.orchestration_service.interface.dependencies.services import (
    get_credential_vault,
)
from agentverse_api.webhook_service.application.webhook_service import WebhookService
from agentverse_api.webhook_service.infrastructure.repositories import (
    SqlDeliveryRepository,
    SqlEndpointRepository,
)


def get_webhook_service(session: AsyncSession = Depends(get_db_session)) -> WebhookService:
    """The vault is the platform's one envelope-encryption implementation.

    Reused from the orchestration composition root rather than
    constructed again here: a second `KeyRing.from_env()` would be a
    second place that has to agree about key versions, and a rotation
    that updated one and not the other would leave rows unreadable.
    """
    return WebhookService(
        endpoints=SqlEndpointRepository(session, get_credential_vault()),
        deliveries=SqlDeliveryRepository(session),
    )
