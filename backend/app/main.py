from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import health
from app.api.v1.router import api_router
from app.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.widget_cors import WidgetPublicCorsMiddleware
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

    # Added AFTER CORSMiddleware — Starlette makes the most-recently-added
    # middleware outermost (confirmed empirically: with the reverse order, a
    # widget request's OPTIONS preflight was intercepted and rejected by
    # CORSMiddleware's fixed dashboard-origin allow-list before ever
    # reaching this one). Being outermost means /api/v1/widget/* requests
    # are handled entirely by this middleware (any origin, no credentials;
    # see its docstring for why that's safe) and never reach
    # CORSMiddleware's dashboard-only allow-list at all.
    app.add_middleware(WidgetPublicCorsMiddleware)

    register_exception_handlers(app)

    # Mounted at both root (/health) and under /api/v1 (/api/v1/health) from the
    # same implementation, so infra health checks and the versioned API agree.
    app.include_router(health.router, tags=["health"])
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
