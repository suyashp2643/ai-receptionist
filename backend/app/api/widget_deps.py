"""Dependencies for the public widget API (app/api/v1/widget_public.py).

Every dependency here resolves trust server-side, starting only from
`public_id` (a URL path parameter) and — where a specific conversation is
being read or written — a visitor capability token presented in a request
header. None of these dependencies ever accept a tenant_id, receptionist_id,
role, or internal config value from the client; see docs/security.md for
the full threat model this implements.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Path, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import Settings, get_settings
from app.core.client_identity import get_client_ip, hash_client_ip
from app.core.domain_validation import extract_origin_hostname, hostname_matches_allowed_domains, is_localhost
from app.core.rate_limit import RateLimiter, get_rate_limiter
from app.models.enums import WidgetInstallationStatus
from app.models.widget_installation import WidgetInstallation
from app.models.widget_visitor_session import WidgetVisitorSession
from app.repositories.widget_installation import get_installation_by_public_id
from app.services.widget_visitor_session_service import InvalidCapabilityTokenError, resolve_session_by_token

WIDGET_TOKEN_HEADER = "X-Widget-Session-Token"

# A single generic detail string for every "this widget/session doesn't
# work" case — see InvalidCapabilityTokenError's docstring for why the
# public API must not let a caller distinguish these from each other.
_WIDGET_NOT_FOUND_DETAIL = "Widget not found."
_SESSION_INVALID_DETAIL = "Invalid or expired widget session."


def get_widget_installation(public_id: str = Path(...), db: Session = Depends(get_db)) -> WidgetInstallation:
    installation = get_installation_by_public_id(db, public_id)
    if installation is None or installation.status == WidgetInstallationStatus.REVOKED:
        # Revoked behaves exactly like "never existed" — a public_id that
        # once worked must not keep confirming its own past existence.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_WIDGET_NOT_FOUND_DETAIL)
    return installation


def get_active_widget_installation(
    installation: WidgetInstallation = Depends(get_widget_installation),
) -> WidgetInstallation:
    """Stricter than get_widget_installation: required for every route that
    creates or advances a conversation. A DRAFT or PAUSED installation can
    still serve GET config (so a dashboard preview or a temporarily paused
    widget can render an accurate "unavailable" state) but must refuse
    everything else."""
    if installation.status != WidgetInstallationStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This widget is not currently active.",
        )
    return installation


def validate_widget_origin(
    request: Request,
    installation: WidgetInstallation = Depends(get_widget_installation),
    settings: Settings = Depends(get_settings),
) -> None:
    """Abuse reduction only — NEVER authorization. A non-browser client can
    omit or forge Origin entirely, so a missing header is deliberately let
    through here (documented in docs/security.md) rather than blocked,
    which would only inconvenience legitimate non-browser testing without
    stopping a determined caller. A *present but disallowed or malformed*
    Origin is rejected, since a real browser embed always sends one that
    should match.

    The dashboard's own origin (`Settings.platform_preview_origins`) is
    always allowed, for every installation, so the "live local preview"
    feature works regardless of what a tenant has configured — this is a
    platform-level trust decision, checked as an exact origin string
    (scheme+host+port), never merged into or inferred from any tenant's own
    `allowed_domains`."""
    origin = request.headers.get("origin")
    if not origin:
        return

    if origin in settings.platform_preview_origins_list:
        return

    hostname = extract_origin_hostname(origin)
    if hostname is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This origin is not permitted.")

    if is_localhost(hostname) and settings.environment == "development":
        return

    if not hostname_matches_allowed_domains(hostname, installation.allowed_domains):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This origin is not permitted.")


def get_widget_session_token(
    token: str | None = Header(default=None, alias=WIDGET_TOKEN_HEADER),
) -> str:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_SESSION_INVALID_DETAIL)
    return token


@dataclass(frozen=True)
class WidgetVisitorContext:
    """The resolved, trusted authorization for one public conversation
    request — the widget-API equivalent of app.api.deps.TenantContext.
    `tenant_id` here is never accepted from the client; it comes only from
    the installation row the capability token was proven to belong to."""

    tenant_id: uuid.UUID
    installation: WidgetInstallation
    session: WidgetVisitorSession


def get_widget_visitor_context(
    conversation_id: uuid.UUID = Path(...),
    installation: WidgetInstallation = Depends(get_active_widget_installation),
    token: str = Depends(get_widget_session_token),
    db: Session = Depends(get_db),
) -> WidgetVisitorContext:
    try:
        session = resolve_session_by_token(
            db,
            raw_token=token,
            widget_installation_id=installation.id,
            conversation_id=conversation_id,
        )
    except InvalidCapabilityTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_SESSION_INVALID_DETAIL) from exc
    return WidgetVisitorContext(tenant_id=installation.tenant_id, installation=installation, session=session)


def get_widget_visitor_context_from_token(
    installation: WidgetInstallation = Depends(get_active_widget_installation),
    token: str = Depends(get_widget_session_token),
    db: Session = Depends(get_db),
) -> WidgetVisitorContext:
    """Same resolution as get_widget_visitor_context, but for routes that
    take no `conversation_id` path parameter at all (contacts,
    appointment-requests, handoff-requests) — the token alone determines
    which conversation the action applies to, since a WidgetVisitorSession
    is always scoped 1:1 to exactly one conversation."""
    try:
        session = resolve_session_by_token(db, raw_token=token, widget_installation_id=installation.id)
    except InvalidCapabilityTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_SESSION_INVALID_DETAIL) from exc
    return WidgetVisitorContext(tenant_id=installation.tenant_id, installation=installation, session=session)


def rate_limit(action: str, *, limit: int, window_seconds: int) -> Callable[..., None]:
    """Dependency factory. Keys on (action, installation public_id, hashed
    client IP) — see app/core/rate_limit.py's InMemoryRateLimiter docstring
    for its single-process limitation. A widget conversation's total
    message count is bounded separately (Settings.widget_max_messages_per_conversation),
    not by this limiter."""

    def _dependency(
        request: Request,
        installation: WidgetInstallation = Depends(get_widget_installation),
        settings: Settings = Depends(get_settings),
        limiter: RateLimiter = Depends(get_rate_limiter),
    ) -> None:
        ip = get_client_ip(request, trust_proxy_headers=settings.trust_proxy_headers)
        key = f"{action}:{installation.public_id}:{hash_client_ip(ip)}"
        result = limiter.check(key, limit=limit, window_seconds=window_seconds)
        if not result.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again shortly.",
                headers={"Retry-After": str(result.retry_after_seconds)},
            )

    return _dependency
