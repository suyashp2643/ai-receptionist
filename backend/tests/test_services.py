import uuid

from app.config import get_settings
from app.core.security import create_access_token
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import make_tenant_with_owner

settings = get_settings()


def _auth_headers(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


def test_create_and_update_service(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    headers = _auth_headers(owner)

    create_response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/services",
        json={"name": "Buyer representation", "price_note": "No cost to buyers", "currency": "usd"},
        headers=headers,
    )
    assert create_response.status_code == 201
    assert create_response.json()["currency"] == "USD"  # normalized to uppercase

    service_id = create_response.json()["id"]
    update_response = db_backed_client.patch(
        f"/api/v1/tenants/{tenant.id}/services/{service_id}", json={"is_active": False}, headers=headers
    )
    assert update_response.status_code == 200
    assert update_response.json()["is_active"] is False


def test_service_location_id_must_belong_to_same_tenant(db_backed_client: TestClient, db_session: Session):
    tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
    tenant_b, owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")

    location_b = db_backed_client.post(
        f"/api/v1/tenants/{tenant_b.id}/locations", json={"name": "Tenant B Office"}, headers=_auth_headers(owner_b)
    ).json()

    # Tenant A tries to link a service to Tenant B's location by UUID alone.
    response = db_backed_client.post(
        f"/api/v1/tenants/{tenant_a.id}/services",
        json={"name": "Sneaky Service", "location_id": location_b["id"]},
        headers=_auth_headers(owner_a),
    )
    assert response.status_code == 422


def test_delete_service(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    headers = _auth_headers(owner)
    service = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/services", json={"name": "Temp Service"}, headers=headers
    ).json()

    delete_response = db_backed_client.delete(f"/api/v1/tenants/{tenant.id}/services/{service['id']}", headers=headers)
    assert delete_response.status_code == 204
    assert (
        db_backed_client.get(f"/api/v1/tenants/{tenant.id}/services/{service['id']}", headers=headers).status_code
        == 404
    )


def test_invalid_currency_rejected(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/services",
        json={"name": "Service", "currency": "dollars"},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 422
