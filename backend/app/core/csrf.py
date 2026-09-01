import hmac

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings, get_settings


def verify_csrf(request: Request, settings: Settings = Depends(get_settings)) -> None:
    """Double-submit cookie check for cookie-authenticated, state-changing routes
    (/auth/refresh, /auth/logout). Bearer-token-authenticated routes don't need
    this — a header the browser won't attach cross-site automatically is not
    vulnerable to CSRF the way an ambient cookie is."""
    cookie_value = request.cookies.get(settings.csrf_cookie_name)
    header_value = request.headers.get("x-csrf-token")

    if not cookie_value or not header_value or not hmac.compare_digest(cookie_value, header_value):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")
