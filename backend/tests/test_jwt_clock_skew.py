"""Deterministic boundary tests for JWT access-token validation, including
the clock-skew leeway added to fix a live-reproduced intermittent 401.

Root cause (see docs/security.md and docs/PROGRESS.md for the full
incident writeup): PyJWT's zero-leeway default rejects a token whenever
the verifying process's wall-clock reading is even slightly *earlier*
than the `iat` reading the issuing process took a moment before. This was
reproduced directly — a tight loop of `create_access_token` immediately
followed by `decode_access_token`, no test framework, no mocking, no HTTP
involved — as `ImmatureSignatureError`, 3 times across roughly 700,000
iterations, each with 600-700ms of measured skew, consistent with this
environment's (WSL2) periodic host time-sync correction.

Every test here crafts its token directly with `jwt.encode` (bypassing
`create_access_token`) so each boundary condition is placed
deterministically — no sleep, no real clock race, no flakiness.
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.config import Settings, get_settings
from app.core.security import (
    AccessTokenPayload,
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
)
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import make_user

_TEST_SECRET = "test-only-signing-secret-not-a-real-credential"  # noqa: S105 - fixture value, not a credential


def _settings(**overrides) -> Settings:
    return Settings(jwt_secret_key=_TEST_SECRET, **overrides)


def _craft_token(
    settings: Settings,
    *,
    iat: datetime,
    exp: datetime,
    secret: str | None = None,
    issuer: str | None = None,
    audience: str | None = None,
) -> str:
    payload = {
        "sub": str(uuid.uuid4()),
        "sid": str(uuid.uuid4()),
        "iat": iat,
        "exp": exp,
        "iss": issuer if issuer is not None else settings.jwt_issuer,
        "aud": audience if audience is not None else settings.jwt_audience,
    }
    return jwt.encode(payload, secret if secret is not None else settings.jwt_secret_key, algorithm="HS256")


class TestClockSkewLeeway:
    def test_token_valid_at_issuance_is_accepted(self):
        settings = _settings()
        token, expires_in = create_access_token(settings=settings, user_id=uuid.uuid4(), session_id=uuid.uuid4())
        payload = decode_access_token(settings=settings, token=token)
        assert isinstance(payload, AccessTokenPayload)
        assert expires_in == settings.access_token_ttl_minutes * 60

    def test_small_acceptable_clock_skew_is_accepted(self):
        settings = _settings(jwt_clock_skew_leeway_seconds=5.0)
        now = datetime.now(UTC)
        # iat 3s in the future — within the 5s leeway (the largest skew
        # actually observed while reproducing this was ~0.7s).
        token = _craft_token(settings, iat=now + timedelta(seconds=3), exp=now + timedelta(minutes=15))
        payload = decode_access_token(settings=settings, token=token)
        assert isinstance(payload, AccessTokenPayload)

    def test_skew_beyond_the_allowance_is_rejected(self):
        settings = _settings(jwt_clock_skew_leeway_seconds=5.0)
        now = datetime.now(UTC)
        token = _craft_token(settings, iat=now + timedelta(seconds=30), exp=now + timedelta(minutes=15))
        with pytest.raises(InvalidAccessTokenError, match="ImmatureSignatureError"):
            decode_access_token(settings=settings, token=token)

    def test_genuinely_expired_token_is_rejected(self):
        settings = _settings(jwt_clock_skew_leeway_seconds=5.0)
        now = datetime.now(UTC)
        token = _craft_token(settings, iat=now - timedelta(minutes=20), exp=now - timedelta(minutes=5))
        with pytest.raises(InvalidAccessTokenError, match="ExpiredSignatureError"):
            decode_access_token(settings=settings, token=token)

    def test_expiration_just_within_the_leeway_is_still_accepted(self):
        """Documents the trade-off explicitly rather than leaving it
        implicit: the same leeway that tolerates an early `iat` also lets
        a token remain valid up to `leeway` seconds past its nominal
        `exp` — deliberate and bounded (2s out of a 900s/15-minute
        lifetime here), not an accidental side effect."""
        settings = _settings(jwt_clock_skew_leeway_seconds=5.0)
        now = datetime.now(UTC)
        token = _craft_token(settings, iat=now - timedelta(minutes=15), exp=now - timedelta(seconds=2))
        payload = decode_access_token(settings=settings, token=token)
        assert isinstance(payload, AccessTokenPayload)

    def test_invalid_issuer_is_rejected(self):
        settings = _settings()
        now = datetime.now(UTC)
        token = _craft_token(settings, iat=now, exp=now + timedelta(minutes=15), issuer="someone-elses-issuer")
        with pytest.raises(InvalidAccessTokenError, match="InvalidIssuerError"):
            decode_access_token(settings=settings, token=token)

    def test_invalid_audience_is_rejected(self):
        settings = _settings()
        now = datetime.now(UTC)
        token = _craft_token(settings, iat=now, exp=now + timedelta(minutes=15), audience="someone-elses-audience")
        with pytest.raises(InvalidAccessTokenError, match="InvalidAudienceError"):
            decode_access_token(settings=settings, token=token)

    def test_invalid_signature_is_rejected(self):
        settings = _settings()
        now = datetime.now(UTC)
        token = _craft_token(
            settings, iat=now, exp=now + timedelta(minutes=15), secret="a-completely-different-secret"
        )
        with pytest.raises(InvalidAccessTokenError, match="InvalidSignatureError"):
            decode_access_token(settings=settings, token=token)

    def test_leeway_never_weakens_signature_issuer_or_audience_checks(self):
        """A large leeway must never be mistaken for, or accidentally
        implemented as, a general validation bypass. Uses a deliberately
        huge leeway for this one check only, to prove it changes nothing
        about signature/issuer/audience enforcement."""
        settings = _settings(jwt_clock_skew_leeway_seconds=3600.0)
        now = datetime.now(UTC)

        bad_sig = _craft_token(settings, iat=now, exp=now + timedelta(minutes=15), secret="wrong-secret")
        with pytest.raises(InvalidAccessTokenError, match="InvalidSignatureError"):
            decode_access_token(settings=settings, token=bad_sig)

        bad_iss = _craft_token(settings, iat=now, exp=now + timedelta(minutes=15), issuer="wrong-issuer")
        with pytest.raises(InvalidAccessTokenError, match="InvalidIssuerError"):
            decode_access_token(settings=settings, token=bad_iss)

        bad_aud = _craft_token(settings, iat=now, exp=now + timedelta(minutes=15), audience="wrong-audience")
        with pytest.raises(InvalidAccessTokenError, match="InvalidAudienceError"):
            decode_access_token(settings=settings, token=bad_aud)


class TestSessionLevelRejection:
    """Not a JWT-validation case — a syntactically and cryptographically
    valid, unexpired token is still rejected if the user it names no
    longer exists or has been deactivated, exercised through the real
    `/auth/me` route rather than `decode_access_token` directly."""

    def test_token_for_a_deactivated_user_is_rejected(self, db_backed_client: TestClient, db_session: Session):
        settings = get_settings()
        user = make_user(db_session)
        token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())

        user.is_active = False
        db_session.flush()

        response = db_backed_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    def test_token_for_a_nonexistent_user_is_rejected(self, db_backed_client: TestClient):
        settings = get_settings()
        token, _ = create_access_token(settings=settings, user_id=uuid.uuid4(), session_id=uuid.uuid4())

        response = db_backed_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
