"""ASGI entrypoint: `uvicorn agentverse_worker.main:app`.

See `interface/__init__.py` for why a background-job service runs an
ASGI app in this phase.
"""

from fastapi import FastAPI

from agentverse_worker.infrastructure.config import get_settings
from agentverse_worker.infrastructure.logging import configure_logging
from agentverse_worker.interface.routes.health import router as health_router


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="AgentVerse Worker",
        version="0.1.0-alpha",
        openapi_url="/openapi.json" if settings.environment != "production" else None,
    )
    app.include_router(health_router)
    return app


app = create_app()
