"""ASGI entrypoint: `uvicorn agentverse_api.main:app`."""

from fastapi import FastAPI

from agentverse_api.auth_service.interface.routes.api_keys import router as api_keys_router
from agentverse_api.auth_service.interface.routes.internal_auth_events import (
    router as internal_auth_events_router,
)
from agentverse_api.auth_service.interface.routes.workspaces import router as workspaces_router
from agentverse_api.infrastructure.config import get_settings
from agentverse_api.infrastructure.logging import configure_logging
from agentverse_api.interface.middleware import request_id_middleware
from agentverse_api.interface.routes.health import router as health_router
from agentverse_api.orchestration_service.interface.routers.internal_job_test import (
    router as internal_job_test_router,
)
from agentverse_api.orchestration_service.interface.routers.internal_provider_test import (
    router as internal_provider_test_router,
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
    app.include_router(api_keys_router)
    app.include_router(internal_auth_events_router)
    app.include_router(internal_provider_test_router)
    app.include_router(internal_job_test_router)
    return app


app = create_app()
