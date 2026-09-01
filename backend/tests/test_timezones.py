import uuid
import zoneinfo

from fastapi.testclient import TestClient


def _register(client: TestClient, *, timezone: str, email: str | None = None):
    email = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
    return client.post(
        "/api/v1/auth/register",
        json={
            "display_name": "Ada Lovelace",
            "email": email,
            "password": "correct horse battery staple",
            "workspace_name": "Ada's Workspace",
            "timezone": timezone,
        },
    )


def test_timezones_endpoint_is_public(client: TestClient):
    """No Authorization header — registration needs this before any session exists."""
    response = client.get("/api/v1/timezones")
    assert response.status_code == 200


def test_timezones_endpoint_returns_backend_valid_list(client: TestClient):
    response = client.get("/api/v1/timezones")
    body = response.json()
    timezones = body["timezones"]
    assert isinstance(timezones, list)
    assert len(timezones) > 0
    assert "UTC" in timezones
    assert "Asia/Kolkata" in timezones
    # Every entry returned must itself be a real, available IANA zone — the
    # endpoint should never expose a name the validator would then reject.
    available = zoneinfo.available_timezones()
    assert set(timezones) <= available


def test_timezones_endpoint_excludes_known_legacy_aliases(client: TestClient):
    """Asia/Calcutta and friends are IANA 'backward' links some ICU/browser
    builds still expose but this backend's zoneinfo database does not."""
    response = client.get("/api/v1/timezones")
    timezones = set(response.json()["timezones"])
    for legacy_alias in ("Asia/Calcutta", "Europe/Kiev", "America/Buenos_Aires"):
        assert legacy_alias not in timezones


def test_registration_accepts_asia_kolkata(db_backed_client: TestClient):
    response = _register(db_backed_client, timezone="Asia/Kolkata")
    assert response.status_code == 201


def test_registration_accepts_utc(db_backed_client: TestClient):
    response = _register(db_backed_client, timezone="UTC")
    assert response.status_code == 201


def test_registration_rejects_asia_calcutta(db_backed_client: TestClient):
    """The exact bug this fix closes: the legacy alias must not be silently
    accepted by the backend, even though some browsers still offer it."""
    response = _register(db_backed_client, timezone="Asia/Calcutta")
    assert response.status_code == 422
    body = response.json()
    assert "Asia/Calcutta" in str(body["error"]["details"])


def test_registration_rejects_arbitrary_invalid_timezone(db_backed_client: TestClient):
    response = _register(db_backed_client, timezone="Not/ARealZone")
    assert response.status_code == 422


def test_every_backend_listed_timezone_is_itself_accepted_on_registration(db_backed_client: TestClient):
    """Round-trip guarantee: anything the frontend could render from
    GET /timezones must itself pass the registration validator — the two
    can never drift since they read the same VALID_TIMEZONES set, but this
    pins that invariant with an explicit end-to-end check rather than
    trusting the shared import alone. Sampled, not exhaustive, to keep the
    test fast."""
    listed = db_backed_client.get("/api/v1/timezones").json()["timezones"]
    sample = listed[:: max(1, len(listed) // 25)]  # ~25 evenly spaced entries
    for tz in sample:
        response = _register(db_backed_client, timezone=tz)
        assert response.status_code == 201, f"{tz} was listed but rejected on registration"
