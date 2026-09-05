import pytest
from app.config import Settings
from fastapi.testclient import TestClient


def test_wildcard_cors_origin_is_rejected_at_config_load():
    """Phase 9 hardening: `app.main` always pairs `cors_origins_list` with
    `allow_credentials=True`, so a `*` origin must never reach
    CORSMiddleware even if an operator misconfigures the environment
    variable — this should fail loudly at settings-access time rather than
    relying solely on browsers to refuse the wildcard-plus-credentials
    combination."""
    settings = Settings(cors_allow_origins="*")
    with pytest.raises(RuntimeError, match="CORS_ALLOW_ORIGINS"):
        _ = settings.cors_origins_list


def test_wildcard_mixed_with_real_origins_is_still_rejected():
    settings = Settings(cors_allow_origins="http://localhost:3000,*")
    with pytest.raises(RuntimeError, match="CORS_ALLOW_ORIGINS"):
        _ = settings.cors_origins_list


def test_allowed_origin_gets_cors_header(client: TestClient):
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_untrusted_origin_gets_no_cors_header(client: TestClient):
    response = client.get("/health", headers={"Origin": "http://evil.example.com"})
    assert response.status_code == 200  # the request itself isn't blocked server-side...
    assert "access-control-allow-origin" not in response.headers  # ...but browsers will block reading it


def test_untrusted_origin_preflight_rejected(client: TestClient):
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 400
