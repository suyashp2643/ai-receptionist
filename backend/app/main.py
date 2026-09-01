from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import health
from app.api.v1.router import api_router
from app.config import get_settings
from app.core.errors import register_exception_handlers
from app.logging_config import configure_logging


def create_app() -> FastAPI:
    """Application factory. Keeps app construction testable and side-effect-free at import time."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title=settings.app_name, version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    # Mounted at both root (/health) and under /api/v1 (/api/v1/health) from the
    # same implementation, so infra health checks and the versioned API agree.
    app.include_router(health.router, tags=["health"])
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
