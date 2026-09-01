import pytest
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    return TestClient(app)
