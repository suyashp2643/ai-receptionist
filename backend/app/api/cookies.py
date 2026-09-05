from fastapi import Response

from app.config import Settings
from app.core.security import generate_csrf_token

# Scoped narrowly to the auth routes that actually need the refresh cookie —
# it should never be sent on ordinary API calls.
_AUTH_COOKIE_PATH = "/api/v1/auth"

# The CSRF cookie is deliberately NOT scoped to `_AUTH_COOKIE_PATH`. Cookie
# `Path` restricts more than which requests a cookie is attached to — it also
# governs whether `document.cookie` exposes it to JS running on a given page,
# matched against THAT PAGE's own URL path, not the backend's. The frontend
# (a separate Next.js origin) never has a page at `/api/v1/auth/*`; every
# dashboard page lives at `/dashboard/*`, `/login`, etc. Scoping the
# JS-readable, double-submit CSRF cookie to `/api/v1/auth` therefore made it
# permanently unreadable by the frontend on every real page — `readCookie()`
# always got `null`, every silent refresh sent no `X-CSRF-Token` header, and
# `verify_csrf` correctly rejected it with 403, which is what actually broke
# session restoration after a full page reload (see docs/PROGRESS.md's Phase
# 8 remediation section). The refresh-token cookie itself is unaffected by
# this — it's HttpOnly (JS never reads it) and correctly stays narrowly
# scoped, since the browser only needs to attach it to requests that are
# themselves under `/api/v1/auth`.
_CSRF_COOKIE_PATH = "/"


def set_auth_cookies(
    response: Response,
    settings: Settings,
    *,
    refresh_token: str,
    refresh_max_age_seconds: int,
    existing_csrf_token: str | None = None,
) -> str:
    """Sets the HttpOnly refresh cookie and a paired, JS-readable CSRF cookie.

    The CSRF token is stable for the life of a login session: refresh/logout
    pass their incoming cookie value back in via `existing_csrf_token` so it
    is only re-set (extending its Max-Age) rather than rotated — there's no
    security reason to rotate it (unlike the refresh token itself), and
    rotating it would force the frontend to re-read it after every silent
    refresh for no benefit. Register/login (no prior session) leave it unset
    and get a freshly generated one.

    Returns the CSRF token so the caller can also return it in the response
    body for the frontend to store and echo back as X-CSRF-Token.
    """
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        max_age=refresh_max_age_seconds,
        httponly=True,
        secure=settings.resolved_cookie_secure,
        samesite=settings.cookie_samesite,
        path=_AUTH_COOKIE_PATH,
    )
    csrf_token = existing_csrf_token or generate_csrf_token()
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        max_age=refresh_max_age_seconds,
        httponly=False,  # must be JS-readable for the double-submit pattern
        secure=settings.resolved_cookie_secure,
        samesite=settings.cookie_samesite,
        path=_CSRF_COOKIE_PATH,
    )
    return csrf_token


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(key=settings.refresh_cookie_name, path=_AUTH_COOKIE_PATH)
    response.delete_cookie(key=settings.csrf_cookie_name, path=_CSRF_COOKIE_PATH)
