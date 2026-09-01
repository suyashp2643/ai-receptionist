from fastapi.testclient import TestClient


def test_allowed_origin_gets_cors_header(client: TestClient):
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_untrusted_origin_gets_no_cors_header(client: TestClient):
    response = client.get("/health", headers={"Origin": "http://evil.example.com"})
    assert response.status_code == 200  # the request itself isn't blocked server-side...
    assert (
        "access-control-allow-origin" not in response.headers
    )  # ...but browsers will block reading it


def test_untrusted_origin_preflight_rejected(client: TestClient):
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 400
