"""Composition root for the billing context — routes depend on these
factories and never build a repository themselves (mirrors
`auth_service`'s `dependencies/services.py`).
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentverse_api.billing_service.application.billing_actions_service import (
    BillingActionsService,
)
from agentverse_api.billing_service.application.entitlement_service import EntitlementService
from agentverse_api.billing_service.application.plan_catalog_service import PlanCatalogService
from agentverse_api.billing_service.application.subscription_service import SubscriptionService
from agentverse_api.billing_service.application.webhook_service import WebhookService
from agentverse_api.billing_service.domain.payment_provider import (
    PaymentProviderPort,
    ProviderNotConfiguredError,
)
from agentverse_api.billing_service.infrastructure.repositories import (
    SqlCustomerRepository,
    SqlPlanRepository,
    SqlSubscriptionRepository,
    SqlWebhookEventRepository,
    SqlWorkspaceUsageRepository,
)
from agentverse_api.billing_service.infrastructure.stripe.adapter import StripePaymentProvider
from agentverse_api.infrastructure.config import Settings, get_settings
from agentverse_api.infrastructure.db import get_db_session


def get_plan_catalog_service(
    session: AsyncSession = Depends(get_db_session),
) -> PlanCatalogService:
    return PlanCatalogService(plans=SqlPlanRepository(session))


def get_entitlement_service(
    session: AsyncSession = Depends(get_db_session),
) -> EntitlementService:
    return EntitlementService(
        catalog=PlanCatalogService(plans=SqlPlanRepository(session)),
        usage=SqlWorkspaceUsageRepository(session),
        subscriptions=SqlSubscriptionRepository(session),
    )


def get_subscription_service(
    session: AsyncSession = Depends(get_db_session),
) -> SubscriptionService:
    return SubscriptionService(
        subscriptions=SqlSubscriptionRepository(session),
        customers=SqlCustomerRepository(session),
        catalog=PlanCatalogService(plans=SqlPlanRepository(session)),
    )


@lru_cache
def _provider(settings: Settings) -> PaymentProviderPort | None:
    """One adapter per process, or `None` when no provider is configured.

    Cached because the adapter holds a Stripe HTTP client and a
    process-lifetime Price-id cache; rebuilding it per request would
    discard both and open a new connection pool on every checkout.

    `None` is a legitimate state, not a failure: local development, CI
    and preview environments run without payment credentials, and the
    routes that need one answer 503 rather than 500-ing on a `None`.
    """
    if not settings.stripe_configured:
        return None
    # Narrowed for the type checker; `stripe_configured` already
    # guarantees both halves are present.
    assert settings.stripe_secret_key is not None  # noqa: S101
    assert settings.stripe_webhook_secret is not None  # noqa: S101
    return StripePaymentProvider(
        secret_key=settings.stripe_secret_key,
        webhook_secret=settings.stripe_webhook_secret,
        api_version=settings.stripe_api_version,
        public_url=settings.api_public_url,
    )


def get_payment_provider(
    settings: Settings = Depends(get_settings),
) -> PaymentProviderPort:
    """The provider, or a 503-mapping error if this environment has none."""
    provider = _provider(settings)
    if provider is None:
        raise ProviderNotConfiguredError
    return provider


def get_billing_actions_service(
    session: AsyncSession = Depends(get_db_session),
    provider: PaymentProviderPort = Depends(get_payment_provider),
) -> BillingActionsService:
    return BillingActionsService(
        provider=provider,
        subscriptions=SubscriptionService(
            subscriptions=SqlSubscriptionRepository(session),
            customers=SqlCustomerRepository(session),
            catalog=PlanCatalogService(plans=SqlPlanRepository(session)),
        ),
        customers=SqlCustomerRepository(session),
        catalog=PlanCatalogService(plans=SqlPlanRepository(session)),
    )


def get_webhook_service(
    session: AsyncSession = Depends(get_db_session),
) -> WebhookService:
    # Deliberately does not depend on `get_payment_provider`: the webhook
    # route resolves the provider itself for signature verification, and
    # coupling this to it would make an unconfigured environment fail at
    # dependency resolution rather than at the one place that can explain
    # why.
    return WebhookService(
        events=SqlWebhookEventRepository(session),
        subscriptions=SubscriptionService(
            subscriptions=SqlSubscriptionRepository(session),
            customers=SqlCustomerRepository(session),
            catalog=PlanCatalogService(plans=SqlPlanRepository(session)),
        ),
        catalog=PlanCatalogService(plans=SqlPlanRepository(session)),
    )
