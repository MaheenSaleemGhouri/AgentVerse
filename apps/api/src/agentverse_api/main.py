"""ASGI entrypoint: `uvicorn agentverse_api.main:app`."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agentverse_api.auth_service.interface.routes.api_keys import router as api_keys_router
from agentverse_api.auth_service.interface.routes.audit_logs import router as audit_logs_router
from agentverse_api.auth_service.interface.routes.internal_auth_events import (
    router as internal_auth_events_router,
)
from agentverse_api.auth_service.interface.routes.internal_sso_providers import (
    router as internal_sso_providers_router,
)
from agentverse_api.auth_service.interface.routes.invitations import (
    router as invitations_router,
)
from agentverse_api.auth_service.interface.routes.ip_allowlist import (
    router as ip_allowlist_router,
)
from agentverse_api.auth_service.interface.routes.organization_settings import (
    router as organization_settings_router,
)
from agentverse_api.auth_service.interface.routes.organizations import (
    router as organizations_router,
)
from agentverse_api.auth_service.interface.routes.rbac import (
    router as rbac_router,
)
from agentverse_api.auth_service.interface.routes.resource_permissions import (
    router as resource_permissions_router,
)
from agentverse_api.auth_service.interface.routes.scim import (
    router as scim_router,
)
from agentverse_api.auth_service.interface.routes.scim_tokens import (
    router as scim_tokens_router,
)
from agentverse_api.auth_service.interface.routes.security import (
    router as security_router,
)
from agentverse_api.auth_service.interface.routes.sso import (
    router as sso_router,
)
from agentverse_api.auth_service.interface.routes.workspace_settings import (
    router as workspace_settings_router,
)
from agentverse_api.auth_service.interface.routes.workspaces import router as workspaces_router
from agentverse_api.billing_service.domain.payment_provider import (
    ProviderError,
    ProviderNotConfiguredError,
)
from agentverse_api.billing_service.interface.routes.billing_actions import (
    router as billing_actions_router,
)
from agentverse_api.billing_service.interface.routes.credits import (
    router as billing_credits_router,
)
from agentverse_api.billing_service.interface.routes.entitlements import (
    router as entitlements_router,
)
from agentverse_api.billing_service.interface.routes.plans import router as plans_router
from agentverse_api.billing_service.interface.routes.subscriptions import (
    router as subscriptions_router,
)
from agentverse_api.billing_service.interface.routes.usage import (
    router as billing_usage_router,
)
from agentverse_api.billing_service.interface.routes.webhooks import (
    router as billing_webhooks_router,
)
from agentverse_api.infrastructure.config import get_settings
from agentverse_api.infrastructure.logging import configure_logging
from agentverse_api.interface.middleware import request_id_middleware
from agentverse_api.interface.routes.health import router as health_router
from agentverse_api.notification_service.interface.routes.notifications import (
    router as notifications_router,
)
from agentverse_api.orchestration_service.interface.routers.agents import (
    router as agents_router,
)
from agentverse_api.orchestration_service.interface.routers.integrations import (
    router as integrations_router,
)
from agentverse_api.orchestration_service.interface.routers.internal_job_test import (
    router as internal_job_test_router,
)
from agentverse_api.orchestration_service.interface.routers.internal_provider_test import (
    router as internal_provider_test_router,
)
from agentverse_api.orchestration_service.interface.routers.knowledge import (
    router as knowledge_router,
)
from agentverse_api.orchestration_service.interface.routers.oauth_callback import (
    router as oauth_callback_router,
)
from agentverse_api.orchestration_service.interface.routers.run_stream import (
    router as run_stream_router,
)
from agentverse_api.orchestration_service.interface.routers.team_session_stream import (
    router as team_session_stream_router,
)
from agentverse_api.orchestration_service.interface.routers.teams import (
    router as teams_router,
)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    # Fails startup rather than the first checkout: a test-mode key in
    # production means customers complete payment and are never charged,
    # and a live-mode key outside production means a test run can move
    # real money. Both are silent until money is involved.
    settings.validate_stripe_mode()

    app = FastAPI(
        title="AgentVerse API",
        version="0.1.0-alpha",
        openapi_url="/openapi.json" if settings.environment != "production" else None,
    )
    app.middleware("http")(request_id_middleware)

    # Payment-provider failures get their own mapping so a provider
    # outage reads as one (502/503) rather than as a bug in this service
    # (500) — and so a provider's exception text never reaches a
    # response body verbatim.
    @app.exception_handler(ProviderNotConfiguredError)
    async def _provider_unconfigured(
        request: Request, exc: ProviderNotConfiguredError
    ) -> JSONResponse:
        del request
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(ProviderError)
    async def _provider_failed(request: Request, exc: ProviderError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=502,
            content={"detail": exc.detail, "retryable": exc.retryable},
        )

    app.include_router(health_router)
    app.include_router(workspaces_router)
    app.include_router(workspace_settings_router)
    app.include_router(organizations_router)
    app.include_router(organization_settings_router)
    app.include_router(invitations_router)
    app.include_router(resource_permissions_router)
    app.include_router(rbac_router)
    app.include_router(security_router)
    app.include_router(ip_allowlist_router)
    app.include_router(sso_router)
    app.include_router(scim_tokens_router)
    # SCIM lives outside `/api/v1` on purpose — see the router's module
    # docstring: RFC 7644 fixes its paths, media type and error shape.
    app.include_router(scim_router)
    app.include_router(internal_sso_providers_router)
    app.include_router(agents_router)
    app.include_router(knowledge_router)
    app.include_router(run_stream_router)
    app.include_router(teams_router)
    app.include_router(integrations_router)
    app.include_router(oauth_callback_router)
    app.include_router(team_session_stream_router)
    app.include_router(plans_router)
    app.include_router(entitlements_router)
    app.include_router(subscriptions_router)
    app.include_router(billing_actions_router)
    app.include_router(billing_usage_router)
    app.include_router(billing_credits_router)
    app.include_router(billing_webhooks_router)
    app.include_router(notifications_router)
    app.include_router(api_keys_router)
    app.include_router(audit_logs_router)
    app.include_router(internal_auth_events_router)
    app.include_router(internal_provider_test_router)
    app.include_router(internal_job_test_router)
    return app


app = create_app()
