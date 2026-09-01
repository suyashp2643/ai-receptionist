import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import Settings

# --- Password hashing (Argon2id) ---
# Defaults chosen by the argon2-cffi maintainers to balance security and
# server cost; not overridden here so security-relevant tuning stays
# centralized in one well-reviewed upstream place rather than reinvented.
_password_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 256

# A precomputed hash of a value nobody will ever submit, used to keep login
# timing similar whether or not the email exists — this is the ONLY reason
# a "password" constant appears in this file, and it is never a credential.
_DUMMY_HASH = _password_hasher.hash("dummy-password-for-timing-only")


class PasswordPolicyError(ValueError):
    pass


def validate_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _password_hasher.verify(password_hash, password)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def run_dummy_password_verification() -> None:
    """Burns roughly the same time as a real verify, for unknown-email login attempts."""
    try:
        _password_hasher.verify(_DUMMY_HASH, "irrelevant")
    except VerifyMismatchError:
        pass


# --- Access tokens (JWT) ---


@dataclass(frozen=True)
class AccessTokenPayload:
    user_id: uuid.UUID
    session_id: uuid.UUID


class InvalidAccessTokenError(Exception):
    pass


def create_access_token(
    *, settings: Settings, user_id: uuid.UUID, session_id: uuid.UUID
) -> tuple[str, int]:
    """Returns (token, expires_in_seconds)."""
    secret = settings.require_jwt_secret()
    now = datetime.now(UTC)
    ttl = timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "iat": now,
        "exp": now + ttl,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token, int(ttl.total_seconds())


def decode_access_token(*, settings: Settings, token: str) -> AccessTokenPayload:
    secret = settings.require_jwt_secret()
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],  # whitelist only — prevents algorithm-confusion attacks
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["sub", "sid", "exp", "iat"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidAccessTokenError(str(exc.__class__.__name__)) from exc

    try:
        return AccessTokenPayload(
            user_id=uuid.UUID(payload["sub"]),
            session_id=uuid.UUID(payload["sid"]),
        )
    except (KeyError, ValueError) as exc:
        raise InvalidAccessTokenError("malformed_claims") from exc


# --- Refresh tokens (opaque, random — never JWTs) ---

_REFRESH_TOKEN_BYTES = 32  # 256 bits of entropy


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(_REFRESH_TOKEN_BYTES)


def hash_refresh_token(raw_token: str) -> str:
    """Fast hash is intentional: this is a high-entropy random token, not a
    human password, so Argon2's deliberate slowness buys nothing here and
    would only add server cost."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# --- CSRF (double-submit cookie) ---


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)
