import uuid

from app.config import get_settings
from app.core.security import create_access_token
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import make_receptionist, make_tenant_with_owner

settings = get_settings()


def _auth_headers(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


def _select_field(**overrides) -> dict:
    field = {
        "key": "preferred_room",
        "label": "Preferred room",
        "type": "single_select",
        "required": False,
        "options": [
            {"value": "standard", "label": "Standard"},
            {"value": "deluxe", "label": "Deluxe"},
        ],
        "display_order": 0,
        "is_sensitive": False,
    }
    field.update(overrides)
    return field


def _patch_workflow(client: TestClient, tenant_id, receptionist_id, headers, fields: list[dict]):
    return client.patch(
        f"/api/v1/tenants/{tenant_id}/receptionists/{receptionist_id}/workflow",
        json={"qualification_schema": {"fields": fields}},
        headers=headers,
    )


def test_valid_select_options_accepted(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    receptionist, _ = make_receptionist(db_session, tenant=tenant)
    headers = _auth_headers(owner)

    response = _patch_workflow(db_backed_client, tenant.id, receptionist.id, headers, [_select_field()])
    assert response.status_code == 200
    assert len(response.json()["qualification_schema"]["fields"][0]["options"]) == 2


def test_empty_options_rejected_for_select_type(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    receptionist, _ = make_receptionist(db_session, tenant=tenant)
    headers = _auth_headers(owner)

    response = _patch_workflow(db_backed_client, tenant.id, receptionist.id, headers, [_select_field(options=[])])
    assert response.status_code == 422


def test_missing_options_rejected_for_select_type(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    receptionist, _ = make_receptionist(db_session, tenant=tenant)
    headers = _auth_headers(owner)

    field = _select_field()
    del field["options"]
    response = _patch_workflow(db_backed_client, tenant.id, receptionist.id, headers, [field])
    assert response.status_code == 422


def test_duplicate_option_values_rejected(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    receptionist, _ = make_receptionist(db_session, tenant=tenant)
    headers = _auth_headers(owner)

    field = _select_field(
        options=[
            {"value": "standard", "label": "Standard"},
            {"value": "standard", "label": "Standard (duplicate)"},
        ]
    )
    response = _patch_workflow(db_backed_client, tenant.id, receptionist.id, headers, [field])
    assert response.status_code == 422


def test_blank_option_label_rejected(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    receptionist, _ = make_receptionist(db_session, tenant=tenant)
    headers = _auth_headers(owner)

    field = _select_field(options=[{"value": "standard", "label": ""}])
    response = _patch_workflow(db_backed_client, tenant.id, receptionist.id, headers, [field])
    assert response.status_code == 422


def test_blank_option_value_rejected(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    receptionist, _ = make_receptionist(db_session, tenant=tenant)
    headers = _auth_headers(owner)

    field = _select_field(options=[{"value": "", "label": "Standard"}])
    response = _patch_workflow(db_backed_client, tenant.id, receptionist.id, headers, [field])
    assert response.status_code == 422


def test_html_in_option_rejected(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    receptionist, _ = make_receptionist(db_session, tenant=tenant)
    headers = _auth_headers(owner)

    field = _select_field(options=[{"value": "standard", "label": "<script>alert(1)</script>"}])
    response = _patch_workflow(db_backed_client, tenant.id, receptionist.id, headers, [field])
    assert response.status_code == 422


def test_unsupported_extra_keys_rejected(db_backed_client: TestClient, db_session: Session):
    """extra="forbid" hardening: an unrecognized structure/key must be
    rejected outright, not silently ignored."""
    tenant, owner, _ = make_tenant_with_owner(db_session)
    receptionist, _ = make_receptionist(db_session, tenant=tenant)
    headers = _auth_headers(owner)

    field = _select_field()
    field["options"][0]["executable"] = "rm -rf /"
    response = _patch_workflow(db_backed_client, tenant.id, receptionist.id, headers, [field])
    assert response.status_code == 422


def test_maximum_option_count_enforced(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    receptionist, _ = make_receptionist(db_session, tenant=tenant)
    headers = _auth_headers(owner)

    field = _select_field(options=[{"value": f"opt{i}", "label": f"Option {i}"} for i in range(31)])
    response = _patch_workflow(db_backed_client, tenant.id, receptionist.id, headers, [field])
    assert response.status_code == 422


def test_maximum_option_count_boundary_accepted(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    receptionist, _ = make_receptionist(db_session, tenant=tenant)
    headers = _auth_headers(owner)

    field = _select_field(options=[{"value": f"opt{i}", "label": f"Option {i}"} for i in range(30)])
    response = _patch_workflow(db_backed_client, tenant.id, receptionist.id, headers, [field])
    assert response.status_code == 200


def test_option_label_max_length_enforced(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    receptionist, _ = make_receptionist(db_session, tenant=tenant)
    headers = _auth_headers(owner)

    field = _select_field(options=[{"value": "standard", "label": "x" * 101}])
    response = _patch_workflow(db_backed_client, tenant.id, receptionist.id, headers, [field])
    assert response.status_code == 422


def test_option_value_max_length_enforced(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    receptionist, _ = make_receptionist(db_session, tenant=tenant)
    headers = _auth_headers(owner)

    field = _select_field(options=[{"value": "x" * 101, "label": "Standard"}])
    response = _patch_workflow(db_backed_client, tenant.id, receptionist.id, headers, [field])
    assert response.status_code == 422


def test_non_select_type_with_options_rejected(db_backed_client: TestClient, db_session: Session):
    """Guards against a client that changed a field's type away from
    select without clearing its options — the backend is the final
    authority regardless of what the frontend does."""
    tenant, owner, _ = make_tenant_with_owner(db_session)
    receptionist, _ = make_receptionist(db_session, tenant=tenant)
    headers = _auth_headers(owner)

    field = _select_field(type="short_text")
    response = _patch_workflow(db_backed_client, tenant.id, receptionist.id, headers, [field])
    assert response.status_code == 422


def test_multi_select_type_supported(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    receptionist, _ = make_receptionist(db_session, tenant=tenant)
    headers = _auth_headers(owner)

    field = _select_field(type="multi_select", key="amenities")
    response = _patch_workflow(db_backed_client, tenant.id, receptionist.id, headers, [field])
    assert response.status_code == 200


def test_select_options_preserved_through_save_and_reload(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    receptionist, _ = make_receptionist(db_session, tenant=tenant)
    headers = _auth_headers(owner)

    field = _select_field(
        options=[
            {"value": "standard", "label": "Standard"},
            {"value": "deluxe", "label": "Deluxe"},
            {"value": "suite", "label": "Suite"},
        ]
    )
    save_response = _patch_workflow(db_backed_client, tenant.id, receptionist.id, headers, [field])
    assert save_response.status_code == 200

    reload_response = db_backed_client.get(
        f"/api/v1/tenants/{tenant.id}/receptionists/{receptionist.id}/workflow", headers=headers
    )
    assert reload_response.status_code == 200
    reloaded_field = reload_response.json()["qualification_schema"]["fields"][0]
    assert reloaded_field["type"] == "single_select"
    assert reloaded_field["options"] == [
        {"value": "standard", "label": "Standard"},
        {"value": "deluxe", "label": "Deluxe"},
        {"value": "suite", "label": "Suite"},
    ]
