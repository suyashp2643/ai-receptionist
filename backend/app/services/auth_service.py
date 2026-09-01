import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.normalization import normalize_email
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    run_dummy_password_verification,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.tenant import Tenant
from app.models.tenant_member import TenantMember
from app.models.user import User
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.schemas.auth import RegisterRequest
from app.services.tenant_service import create_tenant_with_owner


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    """Deliberately generic — callers must not describe *why* login failed
    (unknown email vs. wrong password vs. inactive account all map here)."""


class RefreshTokenInvalidError(Exception):
    pass


class RefreshTokenReuseDetectedError(Exception):
    """Raised when an already-rotated (or already-revoked) refresh token is
    presented again — the whole family has already been revoked by the time
    this is raised, so the caller only needs to reject the request."""


@dataclass(frozen=True)
class IssuedSession:
    access_token: str
    expires_in: int
    raw_refresh_token: str
    refresh_expires_at: datetime
    family_id: uuid.UUID
    refresh_token_id: uuid.UUID


def _issue_session(db: Session, settings: Settings, *, user: User, family_id: uuid.UUID | None) -> IssuedSession:
    family_id = family_id or uuid.uuid4()
    raw_token = generate_refresh_token()
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days)

    row = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_token),
        family_id=family_id,
        expires_at=expires_at,
    )
    RefreshTokenRepository(db).add(row)
    db.flush()  # assigns row.id

    access_token, expires_in = create_access_token(settings=settings, user_id=user.id, session_id=family_id)

    return IssuedSession(
        access_token=access_token,
        expires_in=expires_in,
        raw_refresh_token=raw_token,
        refresh_expires_at=expires_at,
        family_id=family_id,
        refresh_token_id=row.id,
    )


def register_user(
    db: Session, settings: Settings, payload: RegisterRequest
) -> tuple[User, Tenant, TenantMember, IssuedSession]:
    """Registration is one atomic unit: user + tenant + owner membership +
    session, or nothing. The request-scoped session (app/db/session.get_db)
    only commits once, after this function and the route handler both
    return successfully — any exception rolls everything back."""
    normalized_email = normalize_email(payload.email)
    password_hash = hash_password(payload.password)

    user = User(
        normalized_email=normalized_email,
        password_hash=password_hash,
        display_name=payload.display_name,
    )
    UserRepository(db).add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        raise EmailAlreadyRegisteredError() from exc

    tenant, member = create_tenant_with_owner(
        db, user_id=user.id, name=payload.workspace_name, timezone=payload.timezone
    )

    session = _issue_session(db, settings, user=user, family_id=None)

    return user, tenant, member, session


def authenticate_user(db: Session, *, normalized_email: str, password: str) -> User:
    user = UserRepository(db).get_by_normalized_email(normalized_email)

    if user is None:
        run_dummy_password_verification()
        raise InvalidCredentialsError()

    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()

    if not user.is_active:
        raise InvalidCredentialsError()

    return user


def login_user(db: Session, settings: Settings, *, normalized_email: str, password: str) -> tuple[User, IssuedSession]:
    user = authenticate_user(db, normalized_email=normalized_email, password=password)
    user.last_login_at = datetime.now(UTC)
    session = _issue_session(db, settings, user=user, family_id=None)
    return user, session


def refresh_session(db: Session, settings: Settings, *, raw_refresh_token: str) -> tuple[User, IssuedSession]:
    """Rotates a refresh token. Reusing an already-rotated/revoked token
    revokes the entire family (theft/replay signal) before rejecting."""
    repo = RefreshTokenRepository(db)
    presented_hash = hash_refresh_token(raw_refresh_token)
    token = repo.get_by_token_hash(presented_hash)

    if token is None:
        raise RefreshTokenInvalidError()

    now = datetime.now(UTC)

    if token.revoked_at is not None:
        # Reuse of a token that was already rotated away (or already logged
        # out) — treat the whole session family as compromised.
        repo.revoke_family(token.family_id)
        raise RefreshTokenReuseDetectedError()

    if token.expires_at < now:
        repo.revoke(token)
        raise RefreshTokenInvalidError()

    user = UserRepository(db).get_by_id(token.user_id)
    if user is None or not user.is_active:
        repo.revoke_family(token.family_id)
        raise RefreshTokenInvalidError()

    token.last_used_at = now
    new_session = _issue_session(db, settings, user=user, family_id=token.family_id)

    token.revoked_at = now
    token.replaced_by_token_id = new_session.refresh_token_id

    return user, new_session


def logout_session(db: Session, *, raw_refresh_token: str | None) -> None:
    if not raw_refresh_token:
        return
    repo = RefreshTokenRepository(db)
    token = repo.get_by_token_hash(hash_refresh_token(raw_refresh_token))
    if token is None:
        return
    repo.revoke_family(token.family_id)
