import uuid

from app.config import get_settings
from app.core.security import create_access_token
from app.models.enums import TenantMemberRole
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import add_member, make_tenant_with_owner, make_user

settings = get_settings()


def _auth_headers(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


def test_create_location_with_valid_working_hours(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/locations",
        json={
            "name": "Main Office",
            "city": "Springfield",
            "working_hours": {
                "days": [
                    {"day_of_week": 0, "intervals": [{"start": "09:00", "end": "17:00"}]},
                    {"day_of_week": 6, "closed": True},
                ]
            },
        },
        headers=_auth_headers(owner),
    )
    assert response.status_code == 201


def test_overlapping_intervals_rejected(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/locations",
        json={
            "name": "Main Office",
            "working_hours": {
                "days": [
                    {
                        "day_of_week": 0,
                        "intervals": [
                            {"start": "09:00", "end": "13:00"},
                            {"start": "12:00", "end": "17:00"},
                        ],
                    }
                ]
            },
        },
        headers=_auth_headers(owner),
    )
    assert response.status_code == 422


def test_overnight_hours_rejected(db_backed_client: TestClient, db_session: Session):
    """Overnight ranges (end < start) are a documented Phase 3 limitation."""
    tenant, owner, _ = make_tenant_with_owner(db_session)
    response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/locations",
        json={
            "name": "Night Club",
            "working_hours": {"days": [{"day_of_week": 4, "intervals": [{"start": "22:00", "end": "02:00"}]}]},
        },
        headers=_auth_headers(owner),
    )
    assert response.status_code == 422


def test_closed_day_with_intervals_rejected(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/locations",
        json={
            "name": "Main Office",
            "working_hours": {
                "days": [{"day_of_week": 0, "closed": True, "intervals": [{"start": "09:00", "end": "17:00"}]}]
            },
        },
        headers=_auth_headers(owner),
    )
    assert response.status_code == 422


def test_invalid_timezone_rejected(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/locations",
        json={"name": "Main Office", "timezone": "Mars/OlympusMons"},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 422


def test_only_one_primary_location_per_tenant(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    headers = _auth_headers(owner)

    first = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/locations", json={"name": "Office A", "is_primary": True}, headers=headers
    ).json()
    second = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/locations", json={"name": "Office B", "is_primary": True}, headers=headers
    ).json()

    refreshed_first = db_backed_client.get(
        f"/api/v1/tenants/{tenant.id}/locations/{first['id']}", headers=headers
    ).json()
    refreshed_second = db_backed_client.get(
        f"/api/v1/tenants/{tenant.id}/locations/{second['id']}", headers=headers
    ).json()

    assert refreshed_first["is_primary"] is False
    assert refreshed_second["is_primary"] is True


def test_setting_primary_via_update_unsets_previous_primary(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    headers = _auth_headers(owner)

    first = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/locations", json={"name": "Office A", "is_primary": True}, headers=headers
    ).json()
    second = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/locations", json={"name": "Office B"}, headers=headers
    ).json()

    db_backed_client.patch(
        f"/api/v1/tenants/{tenant.id}/locations/{second['id']}", json={"is_primary": True}, headers=headers
    )

    refreshed_first = db_backed_client.get(
        f"/api/v1/tenants/{tenant.id}/locations/{first['id']}", headers=headers
    ).json()
    assert refreshed_first["is_primary"] is False


def test_delete_location(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    headers = _auth_headers(owner)
    location = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/locations", json={"name": "Temp Office"}, headers=headers
    ).json()

    delete_response = db_backed_client.delete(
        f"/api/v1/tenants/{tenant.id}/locations/{location['id']}", headers=headers
    )
    assert delete_response.status_code == 204

    get_response = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/locations/{location['id']}", headers=headers)
    assert get_response.status_code == 404


def test_member_cannot_create_location(db_backed_client: TestClient, db_session: Session):
    tenant, _owner, _ = make_tenant_with_owner(db_session)
    member = make_user(db_session)
    add_member(db_session, tenant=tenant, user=member, role=TenantMemberRole.MEMBER)

    response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/locations", json={"name": "Should Fail"}, headers=_auth_headers(member)
    )
    assert response.status_code == 403
