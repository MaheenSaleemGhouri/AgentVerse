"""ASGI entrypoint: `uvicorn agentverse_api.main:app`."""

from fastapi import FastAPI

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
from agentverse_api.infrastructure.config import get_settings
from agentverse_api.infrastructure.logging import configure_logging
from agentverse_api.interface.middleware import request_id_middleware
from agentverse_api.interface.routes.health import router as health_router
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

    app = FastAPI(
        title="AgentVerse API",
        version="0.1.0-alpha",
        openapi_url="/openapi.json" if settings.environment != "production" else None,
    )
    app.middleware("http")(request_id_middleware)
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
    app.include_router(api_keys_router)
    app.include_router(audit_logs_router)
    app.include_router(internal_auth_events_router)
    app.include_router(internal_provider_test_router)
    app.include_router(internal_job_test_router)
    return app


app = create_app()
