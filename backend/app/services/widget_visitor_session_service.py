import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.security import generate_visitor_capability_token, hash_visitor_capability_token
from app.models.widget_visitor_session import WidgetVisitorSession
from app.repositories.widget_visitor_session import WidgetVisitorSessionRepository, get_session_by_token_hash


class InvalidCapabilityTokenError(Exception):
    """Deliberately one error for "missing", "malformed", "unknown hash",
    "expired", "revoked", and "wrong installation/conversation scope" —
    the public API must return the same safe 401 for all of these (see
    app/api/v1/widget_public.py) rather than a response shape that would
    let a caller distinguish, e.g., "token expired" from "token never
    existed"."""


def issue_session(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    widget_installation_id: uuid.UUID,
    conversation_id: uuid.UUID,
    ttl_hours: int,
    is_platform_preview: bool = False,
) -> tuple[WidgetVisitorSession, str]:
    """Returns (session, raw_token). `raw_token` exists only in this return
    value and the caller's immediate HTTP response — it is never logged,
    stored, or reconstructible from `session.token_hash`.

    `is_platform_preview` must be computed by the caller from the request's
    own Origin header against Settings.platform_preview_origins_list — never
    accept it as a client-supplied field (see WidgetVisitorSession's
    docstring)."""
    raw_token = generate_visitor_capability_token()
    session = WidgetVisitorSession(
        tenant_id=tenant_id,
        widget_installation_id=widget_installation_id,
        conversation_id=conversation_id,
        token_hash=hash_visitor_capability_token(raw_token),
        expires_at=datetime.now(UTC) + timedelta(hours=ttl_hours),
        is_platform_preview=is_platform_preview,
    )
    WidgetVisitorSessionRepository(db, tenant_id).add(session)
    db.flush()
    return session, raw_token


def resolve_session_by_token(
    db: Session,
    *,
    raw_token: str,
    widget_installation_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
) -> WidgetVisitorSession:
    """The real authorization check for every public conversation/action
    route. Always scopes to a specific `widget_installation_id`, and to a
    specific `conversation_id` when the route operates on one — a token
    valid for conversation A can never be used to touch conversation B,
    even under the same installation or tenant."""
    if not raw_token:
        raise InvalidCapabilityTokenError("Missing capability token.")

    token_hash = hash_visitor_capability_token(raw_token)
    session = get_session_by_token_hash(db, token_hash)
    if session is None:
        raise InvalidCapabilityTokenError("Unknown capability token.")
    if session.widget_installation_id != widget_installation_id:
        raise InvalidCapabilityTokenError("Token is not valid for this widget installation.")
    if conversation_id is not None and session.conversation_id != conversation_id:
        raise InvalidCapabilityTokenError("Token is not valid for this conversation.")
    if session.revoked_at is not None:
        raise InvalidCapabilityTokenError("This session has been revoked.")
    if session.expires_at <= datetime.now(UTC):
        raise InvalidCapabilityTokenError("This session has expired.")

    session.last_seen_at = datetime.now(UTC)
    return session


def revoke_session(session: WidgetVisitorSession) -> None:
    session.revoked_at = datetime.now(UTC)
