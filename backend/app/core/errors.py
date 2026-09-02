import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")


def register_exception_handlers(app: FastAPI) -> None:
    """Central error handling: every error response uses one consistent shape."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # `detail` is usually a plain string, but nothing stops a route from
        # raising HTTPException(detail=<a dict/list/model>) — jsonable_encoder
        # here is the same defensive fix as the validation handler below,
        # applied proactively rather than waiting to discover another case
        # the hard way.
        #
        # `headers=exc.headers` matters: this handler replaces FastAPI's
        # default HTTPException response entirely, and without forwarding
        # `exc.headers` explicitly, any header a route attaches via
        # `HTTPException(..., headers={...})` (e.g. the public widget rate
        # limiter's `Retry-After` on a 429) is silently dropped — caught live
        # via a real 429 response missing `Retry-After` during Phase 5 E2E
        # verification, not from reading the code.
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"message": jsonable_encoder(exc.detail), "status_code": exc.status_code}},
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # exc.errors() can contain a raw exception object in ctx["error"] for
        # any custom `@field_validator` that raises ValueError — plain
        # JSONResponse does NOT run content through jsonable_encoder (unlike
        # FastAPI's own default handler), so passing it straight through
        # crashes the handler itself instead of returning a 422.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": {"message": "Validation error", "details": jsonable_encoder(exc.errors())}},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": {"message": "Internal server error"}},
        )
