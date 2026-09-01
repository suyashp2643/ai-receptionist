from fastapi import Response

from app.config import Settings
from app.core.security import generate_csrf_token

# Scoped narrowly to the auth routes that actually need the refresh cookie —
# it should never be sent on ordinary API calls.
_AUTH_COOKIE_PATH = "/api/v1/auth"


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
        path=_AUTH_COOKIE_PATH,
    )
    return csrf_token


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(key=settings.refresh_cookie_name, path=_AUTH_COOKIE_PATH)
    response.delete_cookie(key=settings.csrf_cookie_name, path=_AUTH_COOKIE_PATH)
