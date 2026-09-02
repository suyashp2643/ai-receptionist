"""Regression coverage for app/core/widget_cors.py — this exists because a
live browser test caught a real bug: the dashboard's credentialed
CORSMiddleware was leaking `Access-Control-Allow-Credentials: true` onto
public widget responses alongside a reflected `Access-Control-Allow-Origin`,
which is exactly the "any origin + credentials" pattern that must never
apply to an unauthenticated public API."""

from fastapi.testclient import TestClient


class TestWidgetCors:
    def test_reflects_any_origin_without_credentials(self, client: TestClient):
        response = client.get(
            "/api/v1/widget/does-not-exist/config", headers={"Origin": "https://third-party-site.example"}
        )
        assert response.headers.get("access-control-allow-origin") == "https://third-party-site.example"
        assert "access-control-allow-credentials" not in response.headers

    def test_preflight_never_advertises_credentials(self, client: TestClient):
        response = client.options(
            "/api/v1/widget/does-not-exist/config",
            headers={"Origin": "https://third-party-site.example", "Access-Control-Request-Method": "GET"},
        )
        assert response.status_code == 204
        assert response.headers.get("access-control-allow-origin") == "https://third-party-site.example"
        assert "access-control-allow-credentials" not in response.headers

    def test_dashboard_routes_keep_credentialed_cors_for_their_allowed_origin(self, client: TestClient):
        response = client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})
        assert response.headers.get("access-control-allow-credentials") == "true"
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_dashboard_routes_do_not_reflect_an_arbitrary_origin(self, client: TestClient):
        response = client.get("/api/v1/health", headers={"Origin": "https://third-party-site.example"})
        assert response.headers.get("access-control-allow-origin") != "https://third-party-site.example"
