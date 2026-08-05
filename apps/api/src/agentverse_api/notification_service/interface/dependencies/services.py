"""Composition root for the notification context."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.infrastructure.config import Settings, get_settings
from agentverse_api.infrastructure.db import get_db_session
from agentverse_api.notification_service.application.billing_notifier import BillingNotifier
from agentverse_api.notification_service.application.notification_service import (
    NotificationService,
)
from agentverse_api.notification_service.infrastructure.email.logging_sender import (
    LoggingEmailSender,
)
from agentverse_api.notification_service.infrastructure.repositories import (
    SqlDeliveryRepository,
    SqlNotificationRepository,
)


def build_notification_service(session: AsyncSession, settings: Settings) -> NotificationService:
    """Shared by the HTTP dependency and by the billing context's own
    composition, so both get an identically-configured service rather
    than two that could drift on `app_base_url`.
    """
    return NotificationService(
        notifications=SqlNotificationRepository(session),
        deliveries=SqlDeliveryRepository(session),
        # No transactional email vendor is configured for this project;
        # the adapter logs what it would have sent. Swapping in a real
        # one is a new class and this one line.
        email=LoggingEmailSender(),
        # Emails need an absolute URL where the in-app entry keeps a
        # relative path — `auth_public_url` is the browser-facing origin
        # a customer actually reaches this app on.
        app_base_url=settings.auth_public_url.rstrip("/"),
    )


def get_notification_service(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> NotificationService:
    return build_notification_service(session, settings)


def get_billing_notifier(
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> BillingNotifier:
    return BillingNotifier(notifications=build_notification_service(session, settings))
