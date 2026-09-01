import uuid

from app.config import get_settings
from app.core.security import create_access_token
from app.models.enums import TenantMemberRole
from app.repositories.industry_template import IndustryTemplateRepository
from app.seed_data.seed_runner import seed_industry_templates
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import add_member, make_receptionist, make_tenant_with_owner, make_user

settings = get_settings()


def _auth_headers(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


def test_owner_can_create_and_update_receptionist(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)

    create_response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/receptionists",
        json={"name": "Ava", "welcome_message": "Hi there!"},
        headers=_auth_headers(owner),
    )
    assert create_response.status_code == 201
    receptionist_id = create_response.json()["id"]

    update_response = db_backed_client.patch(
        f"/api/v1/tenants/{tenant.id}/receptionists/{receptionist_id}",
        json={"name": "Ava Renamed"},
        headers=_auth_headers(owner),
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Ava Renamed"


def test_admin_can_create_and_update_receptionist(db_backed_client: TestClient, db_session: Session):
    tenant, _owner, _ = make_tenant_with_owner(db_session)
    admin = make_user(db_session)
    add_member(db_session, tenant=tenant, user=admin, role=TenantMemberRole.ADMIN)

    response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/receptionists", json={"name": "Ava"}, headers=_auth_headers(admin)
    )
    assert response.status_code == 201


def test_member_can_read_but_not_create_receptionist(db_backed_client: TestClient, db_session: Session):
    tenant, _owner, _ = make_tenant_with_owner(db_session)
    member = make_user(db_session)
    add_member(db_session, tenant=tenant, user=member, role=TenantMemberRole.MEMBER)
    receptionist, _workflow = make_receptionist(db_session, tenant=tenant)

    read_response = db_backed_client.get(
        f"/api/v1/tenants/{tenant.id}/receptionists/{receptionist.id}", headers=_auth_headers(member)
    )
    assert read_response.status_code == 200

    create_response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/receptionists", json={"name": "Should Fail"}, headers=_auth_headers(member)
    )
    assert create_response.status_code == 403


def test_non_member_receives_404(db_backed_client: TestClient, db_session: Session):
    tenant, _owner, _ = make_tenant_with_owner(db_session)
    receptionist, _workflow = make_receptionist(db_session, tenant=tenant)
    outsider = make_user(db_session)

    response = db_backed_client.get(
        f"/api/v1/tenants/{tenant.id}/receptionists/{receptionist.id}", headers=_auth_headers(outsider)
    )
    assert response.status_code == 404


def test_unauthenticated_is_rejected(db_backed_client: TestClient, db_session: Session):
    tenant, _owner, _ = make_tenant_with_owner(db_session)
    response = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/receptionists")
    assert response.status_code == 401


def test_workflow_always_exists_for_a_created_receptionist(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    create_response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/receptionists", json={"name": "Ava"}, headers=_auth_headers(owner)
    )
    receptionist_id = create_response.json()["id"]

    workflow_response = db_backed_client.get(
        f"/api/v1/tenants/{tenant.id}/receptionists/{receptionist_id}/workflow", headers=_auth_headers(owner)
    )
    assert workflow_response.status_code == 200


def test_enabled_actions_reject_unknown_values(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    receptionist, _workflow = make_receptionist(db_session, tenant=tenant)

    response = db_backed_client.patch(
        f"/api/v1/tenants/{tenant.id}/receptionists/{receptionist.id}/workflow",
        json={"enabled_actions": ["answer_questions", "launch_missiles"]},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 422


def test_mandatory_clinic_safety_rules_cannot_be_removed(db_backed_client: TestClient, db_session: Session):
    seed_industry_templates(db_session)
    tenant, owner, _ = make_tenant_with_owner(db_session)

    db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/select-industry",
        json={"template_key": "clinic"},
        headers=_auth_headers(owner),
    )
    receptionist_id = db_backed_client.get(
        f"/api/v1/tenants/{tenant.id}/receptionists", headers=_auth_headers(owner)
    ).json()[0]["id"]

    response = db_backed_client.patch(
        f"/api/v1/tenants/{tenant.id}/receptionists/{receptionist_id}/workflow",
        json={"safety_rules": ["We provide full medical diagnoses over chat."]},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 422
    assert "mandatory" in response.json()["error"]["message"].lower()


def test_mandatory_law_firm_safety_rules_cannot_be_removed(db_backed_client: TestClient, db_session: Session):
    seed_industry_templates(db_session)
    tenant, owner, _ = make_tenant_with_owner(db_session)

    db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/select-industry",
        json={"template_key": "law_firm"},
        headers=_auth_headers(owner),
    )
    receptionist_id = db_backed_client.get(
        f"/api/v1/tenants/{tenant.id}/receptionists", headers=_auth_headers(owner)
    ).json()[0]["id"]

    response = db_backed_client.patch(
        f"/api/v1/tenants/{tenant.id}/receptionists/{receptionist_id}/workflow",
        json={"safety_rules": []},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 422


def test_workflow_update_accepting_full_mandatory_rules_succeeds(db_backed_client: TestClient, db_session: Session):
    seed_industry_templates(db_session)
    tenant, owner, _ = make_tenant_with_owner(db_session)

    db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/select-industry",
        json={"template_key": "clinic"},
        headers=_auth_headers(owner),
    )
    receptionist_id = db_backed_client.get(
        f"/api/v1/tenants/{tenant.id}/receptionists", headers=_auth_headers(owner)
    ).json()[0]["id"]
    template = IndustryTemplateRepository(db_session).get_latest_active_by_key("clinic")

    response = db_backed_client.patch(
        f"/api/v1/tenants/{tenant.id}/receptionists/{receptionist_id}/workflow",
        json={"safety_rules": [*template.default_safety_rules, "Also be extra polite."]},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 200
