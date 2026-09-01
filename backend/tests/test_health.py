from app.config import get_settings
from app.db import session as db_session
from fastapi.testclient import TestClient


def test_root_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("ok", "degraded")
    assert body["database"]["status"] in ("ok", "not_configured", "unavailable")


def test_api_v1_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("ok", "degraded")
    assert body["service"]
    assert body["database"]["status"] in ("ok", "not_configured", "unavailable")


def test_unknown_route_returns_consistent_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert "error" in body
    assert "message" in body["error"]


def test_health_reports_degraded_when_database_unreachable(monkeypatch) -> None:
    """DB configured but unreachable must degrade the response, never crash it."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@127.0.0.1:59999/db")
    get_settings.cache_clear()
    db_session._engine = None
    db_session._session_factory = None

    from app.main import create_app

    client = TestClient(create_app())
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"]["status"] == "unavailable"

    get_settings.cache_clear()
    db_session._engine = None
    db_session._session_factory = None
