"""CORS for the public widget API is deliberately handled separately from
the dashboard's `CORSMiddleware` (app/main.py), because the two have
fundamentally different trust models:

- The dashboard API is only ever called from this product's own frontend,
  so a fixed origin allow-list (`Settings.cors_allow_origins`) is correct
  and sufficient.
- The public widget API is, by design, meant to be embedded on arbitrary
  third-party customer domains that are only known at runtime (stored per
  `WidgetInstallation.allowed_domains` in the database) — a static
  app-config allow-list can never enumerate them in advance.

Browser CORS is NOT this API's authorization boundary (see
app/api/widget_deps.py's `validate_widget_origin` docstring — Origin
validation there is abuse reduction only, and a visitor capability token is
the real authorization). Reflecting any Origin here is therefore safe
PROVIDED credentials are never involved: this API uses a bearer-style
custom header (`X-Widget-Session-Token`), never cookies, so
`Access-Control-Allow-Credentials` is never set to `true` here — an
unauthenticated wildcard-equivalent response is exactly what a
non-credentialed public API is supposed to return, and is not the
"wildcard + credentials" anti-pattern the Phase 5 spec warns against.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

WIDGET_API_PATH_PREFIX = "/api/v1/widget/"
_ALLOWED_METHODS = "GET, POST, OPTIONS"
_ALLOWED_HEADERS = "Content-Type, X-Widget-Session-Token"


class WidgetPublicCorsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(WIDGET_API_PATH_PREFIX):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin")

        if scope["method"] == "OPTIONS":
            response_headers = [
                (b"access-control-allow-methods", _ALLOWED_METHODS.encode()),
                (b"access-control-allow-headers", _ALLOWED_HEADERS.encode()),
                (b"access-control-max-age", b"600"),
            ]
            if origin:
                response_headers.append((b"access-control-allow-origin", origin))
            await send({"type": "http.response.start", "status": 204, "headers": response_headers})
            await send({"type": "http.response.body", "body": b""})
            return

        async def send_with_cors(message: Message) -> None:
            if message["type"] == "http.response.start":
                # Strip whatever the inner (dashboard) CORSMiddleware may have
                # already added — most importantly `Access-Control-Allow-
                # Credentials: true`. That header combined with this
                # middleware's own reflected-origin `Allow-Origin` below would
                # otherwise be exactly the "any origin + credentials" pattern
                # docs/security.md prohibits, regardless of the inner
                # middleware's own dashboard-only intentions.
                message_headers = [
                    (k, v) for k, v in message.get("headers", []) if not k.lower().startswith(b"access-control-")
                ]
                if origin:
                    message_headers.append((b"access-control-allow-origin", origin))
                    message_headers.append((b"vary", b"Origin"))
                message["headers"] = message_headers
            await send(message)

        await self.app(scope, receive, send_with_cors)
