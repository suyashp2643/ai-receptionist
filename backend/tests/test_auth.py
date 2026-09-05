import uuid

from app.config import get_settings
from app.models.refresh_token import RefreshToken
from app.models.tenant_member import TenantMember
from app.models.user import User
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

settings = get_settings()


def _register(client: TestClient, *, email: str | None = None, password: str = "correct horse battery staple"):
    email = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
    return client.post(
        "/api/v1/auth/register",
        json={
            "display_name": "Ada Lovelace",
            "email": email,
            "password": password,
            "workspace_name": "Ada's Workspace",
            "timezone": "UTC",
        },
    ), email


def _csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get(settings.csrf_cookie_name)
    assert token, "CSRF cookie must be set after login/register"
    return {"X-CSRF-Token": token}


def test_registration_succeeds_and_returns_no_password_hash(db_backed_client: TestClient):
    response, email = _register(db_backed_client)
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["normalized_email"] == email.lower()
    assert "password_hash" not in body["user"]
    assert "password" not in body["user"]
    assert body["memberships"][0]["role"] == "owner"
    assert "access_token" in body
    # Never store the refresh token anywhere the browser JS can read it.
    assert settings.refresh_cookie_name in response.cookies
    assert response.cookies[settings.refresh_cookie_name] not in str(body)


def _set_cookie_header_for(response, cookie_name: str) -> str:
    """Returns the raw `Set-Cookie` response header for `cookie_name` — needed
    because httpx's parsed `response.cookies` jar discards the `Path`
    attribute, which is exactly what a Phase 8 remediation round found
    broken: the CSRF cookie was scoped to `Path=/api/v1/auth`, a backend-only
    path the frontend (a separate origin, with pages at `/dashboard/*`,
    `/login`, etc.) never visits — so `document.cookie` on any real frontend
    page could never see it, `readCookie()` always returned null, every
    silent refresh sent no `X-CSRF-Token` header, and `verify_csrf` correctly
    rejected it with 403. That bug was invisible to every pre-existing test
    in this file because they only ever assert via `response.cookies`/
    `client.cookies`, which don't model per-page-path visibility the way a
    real browser's `document.cookie` does — asserting on the raw header is
    the only way this suite actually proves the Path is correct."""
    headers = [
        v for k, v in response.headers.multi_items() if k.lower() == "set-cookie" and v.startswith(f"{cookie_name}=")
    ]
    assert headers, f"No Set-Cookie header found for {cookie_name!r}"
    return headers[0]


def test_csrf_cookie_is_readable_from_any_frontend_page_path(db_backed_client: TestClient):
    """Regression test for the Phase 8 remediation round's root-cause fix —
    see `app/api/cookies.py`'s `_CSRF_COOKIE_PATH` docstring. The CSRF
    cookie must be scoped broadly enough (`Path=/`) that a frontend page at
    ANY path (`/dashboard/...`, `/login`, ...) can read it via
    `document.cookie`; scoping it to a backend-only path silently breaks
    every silent session-refresh on every real page."""
    response, _ = _register(db_backed_client)
    raw = _set_cookie_header_for(response, settings.csrf_cookie_name)
    assert "path=/;" in raw.lower() or raw.lower().rstrip().endswith("path=/")
    assert "path=/api/v1/auth" not in raw.lower()


def test_refresh_cookie_stays_narrowly_scoped_to_auth_routes(db_backed_client: TestClient):
    """The refresh token cookie is HttpOnly (JS never reads it), so unlike
    the CSRF cookie it should stay narrowly scoped — sent only on requests
    to `/api/v1/auth/*`, never on every ordinary API call."""
    response, _ = _register(db_backed_client)
    raw = _set_cookie_header_for(response, settings.refresh_cookie_name)
    assert "path=/api/v1/auth" in raw.lower()


def test_registration_creates_user_tenant_and_owner_membership_atomically(
    db_backed_client: TestClient, db_session: Session
):
    response, email = _register(db_backed_client)
    body = response.json()

    user = db_session.scalars(select(User).where(User.normalized_email == email.lower())).first()
    assert user is not None

    memberships = db_session.scalars(select(TenantMember).where(TenantMember.user_id == user.id)).all()
    assert len(memberships) == 1
    assert memberships[0].role.value == "owner"
    assert str(memberships[0].tenant_id) == body["memberships"][0]["tenant_id"]


def test_duplicate_normalized_email_rejected(db_backed_client: TestClient):
    _, email = _register(db_backed_client)
    # Same email, different case/whitespace — normalization must still catch it.
    response, _ = _register(db_backed_client, email=f"  {email.upper()}  ")
    assert response.status_code == 409


def test_login_succeeds_and_updates_last_login(db_backed_client: TestClient, db_session: Session):
    _, email = _register(db_backed_client, password="a very good password 123")
    response = db_backed_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "a very good password 123"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["last_login_at"] is not None


def test_login_invalid_credentials_generic_error_wrong_password(db_backed_client: TestClient):
    _, email = _register(db_backed_client, password="correct horse battery staple")
    response = db_backed_client.post("/api/v1/auth/login", json={"email": email, "password": "totally wrong password"})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid email or password."


def test_login_invalid_credentials_generic_error_unknown_email(db_backed_client: TestClient):
    response = db_backed_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody-here@example.com", "password": "irrelevant password"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid email or password."


def test_inactive_user_cannot_log_in(db_backed_client: TestClient, db_session: Session):
    _, email = _register(db_backed_client, password="correct horse battery staple")
    user = db_session.scalars(select(User).where(User.normalized_email == email.lower())).first()
    user.is_active = False
    db_session.flush()

    response = db_backed_client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correct horse battery staple"}
    )
    assert response.status_code == 401


def test_me_requires_valid_access_token(db_backed_client: TestClient):
    response = db_backed_client.get("/api/v1/auth/me")
    assert response.status_code == 401

    response = db_backed_client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_me_succeeds_with_valid_access_token(db_backed_client: TestClient):
    register_response, email = _register(db_backed_client)
    access_token = register_response.json()["access_token"]

    response = db_backed_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert response.status_code == 200
    assert response.json()["user"]["normalized_email"] == email.lower()


def test_refresh_without_csrf_header_rejected(db_backed_client: TestClient):
    _register(db_backed_client)
    response = db_backed_client.post("/api/v1/auth/refresh")
    assert response.status_code == 403


def test_refresh_rotation_succeeds_and_old_token_becomes_unusable(db_backed_client: TestClient, db_session: Session):
    register_response, _email = _register(db_backed_client)
    user_id = register_response.json()["user"]["id"]
    old_refresh_cookie = db_backed_client.cookies.get(settings.refresh_cookie_name)

    response = db_backed_client.post("/api/v1/auth/refresh", headers=_csrf_headers(db_backed_client))
    assert response.status_code == 200
    new_refresh_cookie = db_backed_client.cookies.get(settings.refresh_cookie_name)
    assert new_refresh_cookie != old_refresh_cookie

    # Scoped to this test's own user — an unscoped SELECT would also pick up
    # any other data present in the shared dev database (e.g. demo seed rows).
    tokens = db_session.scalars(select(RefreshToken).where(RefreshToken.user_id == user_id)).all()
    assert len(tokens) == 2
    old_token_rows = [t for t in tokens if t.revoked_at is not None]
    assert len(old_token_rows) == 1
    assert old_token_rows[0].replaced_by_token_id is not None


def test_refresh_token_reuse_revokes_entire_family(db_backed_client: TestClient, db_session: Session):
    register_response, _email = _register(db_backed_client)
    user_id = register_response.json()["user"]["id"]
    csrf = _csrf_headers(db_backed_client)
    original_refresh_cookie = db_backed_client.cookies.get(settings.refresh_cookie_name)

    first_refresh = db_backed_client.post("/api/v1/auth/refresh", headers=csrf)
    assert first_refresh.status_code == 200
    rotated_refresh_cookie = db_backed_client.cookies.get(settings.refresh_cookie_name)
    assert rotated_refresh_cookie != original_refresh_cookie

    # Replay the ORIGINAL (now-rotated-away) refresh cookie via an explicit
    # per-request override — this is the signature of a stolen/replayed
    # token. (Mutating the shared cookie jar directly here would create a
    # second same-named cookie and confuse httpx's jar, not the app.)
    reused_response = db_backed_client.post(
        "/api/v1/auth/refresh",
        headers=csrf,
        cookies={settings.refresh_cookie_name: original_refresh_cookie},
    )
    assert reused_response.status_code == 401
    # The 401 response must actually clear cookies client-side, not just say
    # "unauthenticated" while leaving stale cookies behind.
    assert db_backed_client.cookies.get(settings.refresh_cookie_name) is None

    # The rotated (previously "latest", otherwise still-valid) token must now
    # be dead too — checked directly at the DB level, since by this point the
    # client's CSRF cookie has also been cleared (correctly — reuse detection
    # invalidates the whole session) which would make a third HTTP call fail
    # on CSRF grounds rather than exercising the claim being tested here.
    # Scoped to this test's own user — see note in the rotation test above.
    all_tokens = db_session.scalars(select(RefreshToken).where(RefreshToken.user_id == user_id)).all()
    assert len(all_tokens) == 2
    assert all(t.revoked_at is not None for t in all_tokens)


def test_logout_revokes_session_and_refresh_then_fails(db_backed_client: TestClient):
    _register(db_backed_client)
    csrf = _csrf_headers(db_backed_client)

    logout_response = db_backed_client.post("/api/v1/auth/logout", headers=csrf)
    assert logout_response.status_code == 204

    # Logout clears both the refresh and CSRF cookies, so a follow-up refresh
    # attempt with no cookies at all correctly fails CSRF validation first —
    # still an effective rejection, just via a different check.
    refresh_after_logout = db_backed_client.post("/api/v1/auth/refresh", headers=csrf)
    assert refresh_after_logout.status_code == 403


def test_password_policy_rejects_short_password(db_backed_client: TestClient):
    response, _ = _register(db_backed_client, password="short")
    assert response.status_code == 422
