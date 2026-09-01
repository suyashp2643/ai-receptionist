import uuid

from app.config import get_settings
from app.core.security import create_access_token
from app.models.enums import TenantMemberRole
from app.seed_data.seed_runner import seed_industry_templates
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import add_member, make_tenant_with_owner, make_user

settings = get_settings()


def _auth_headers(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


def _bring_to_minimal_valid_config(client: TestClient, tenant_id, headers: dict[str, str]) -> str:
    """Shared setup: business profile + industry + named, active receptionist
    + one enabled action + one active FAQ — the full minimum bar. Returns the
    receptionist id."""
    client.patch(f"/api/v1/tenants/{tenant_id}/business-profile", json={"business_name": "Acme Co"}, headers=headers)
    client.post(f"/api/v1/tenants/{tenant_id}/select-industry", json={"template_key": "saas"}, headers=headers)
    receptionist_id = client.get(f"/api/v1/tenants/{tenant_id}/receptionists", headers=headers).json()[0]["id"]
    client.patch(
        f"/api/v1/tenants/{tenant_id}/receptionists/{receptionist_id}",
        json={"welcome_message": "Welcome to Acme!", "status": "active"},
        headers=headers,
    )
    client.patch(
        f"/api/v1/tenants/{tenant_id}/receptionists/{receptionist_id}/workflow",
        json={"enabled_actions": ["answer_questions"]},
        headers=headers,
    )
    client.post(f"/api/v1/tenants/{tenant_id}/faqs", json={"question": "Q?", "answer": "A."}, headers=headers)
    return receptionist_id


def test_onboarding_state_starts_not_started(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    response = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/onboarding", headers=_auth_headers(owner))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_started"
    assert body["ready_to_complete"] is False
    assert len(body["incomplete_requirements"]) > 0


def test_business_profile_update_moves_status_to_in_progress(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    headers = _auth_headers(owner)

    db_backed_client.patch(
        f"/api/v1/tenants/{tenant.id}/business-profile",
        json={"business_name": "Acme Co"},
        headers=headers,
    )
    state = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/onboarding", headers=headers).json()
    assert state["status"] == "in_progress"
    assert state["steps"]["business_profile"] is True


def test_cannot_complete_onboarding_without_minimum_configuration(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    response = db_backed_client.post(f"/api/v1/tenants/{tenant.id}/complete-onboarding", headers=_auth_headers(owner))
    assert response.status_code == 422
    body = response.json()
    codes = {r["code"] for r in body["error"]["requirements"]}
    assert "business_profile" in codes
    assert "industry_template" in codes
    assert "receptionist_named" in codes


def test_missing_knowledge_is_reported(db_backed_client: TestClient, db_session: Session):
    seed_industry_templates(db_session)
    tenant, owner, _ = make_tenant_with_owner(db_session)
    headers = _auth_headers(owner)

    receptionist_id = _bring_to_minimal_valid_config(db_backed_client, tenant.id, headers)
    # Deactivate the only FAQ so knowledge is missing again.
    faqs = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/faqs", headers=headers).json()
    db_backed_client.patch(
        f"/api/v1/tenants/{tenant.id}/faqs/{faqs[0]['id']}", json={"is_active": False}, headers=headers
    )

    response = db_backed_client.post(f"/api/v1/tenants/{tenant.id}/complete-onboarding", headers=headers)
    assert response.status_code == 422
    codes = {r["code"] for r in response.json()["error"]["requirements"]}
    assert codes == {"knowledge_or_faq"}
    assert receptionist_id  # sanity: setup actually ran


def test_missing_or_invalid_workflow_is_reported(db_backed_client: TestClient, db_session: Session):
    seed_industry_templates(db_session)
    tenant, owner, _ = make_tenant_with_owner(db_session)
    headers = _auth_headers(owner)

    _bring_to_minimal_valid_config(db_backed_client, tenant.id, headers)
    receptionist_id = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/receptionists", headers=headers).json()[0][
        "id"
    ]
    # Pause the receptionist — workflow_active should now be reported.
    db_backed_client.patch(
        f"/api/v1/tenants/{tenant.id}/receptionists/{receptionist_id}", json={"status": "paused"}, headers=headers
    )

    response = db_backed_client.post(f"/api/v1/tenants/{tenant.id}/complete-onboarding", headers=headers)
    assert response.status_code == 422
    codes = {r["code"] for r in response.json()["error"]["requirements"]}
    assert codes == {"workflow_active"}


def test_missing_enabled_actions_is_reported(db_backed_client: TestClient, db_session: Session):
    seed_industry_templates(db_session)
    tenant, owner, _ = make_tenant_with_owner(db_session)
    headers = _auth_headers(owner)

    receptionist_id = _bring_to_minimal_valid_config(db_backed_client, tenant.id, headers)
    db_backed_client.patch(
        f"/api/v1/tenants/{tenant.id}/receptionists/{receptionist_id}/workflow",
        json={"enabled_actions": []},
        headers=headers,
    )

    response = db_backed_client.post(f"/api/v1/tenants/{tenant.id}/complete-onboarding", headers=headers)
    assert response.status_code == 422
    codes = {r["code"] for r in response.json()["error"]["requirements"]}
    assert codes == {"enabled_actions"}


def test_valid_minimal_configuration_completes_successfully(db_backed_client: TestClient, db_session: Session):
    seed_industry_templates(db_session)
    tenant, owner, _ = make_tenant_with_owner(db_session)
    headers = _auth_headers(owner)

    _bring_to_minimal_valid_config(db_backed_client, tenant.id, headers)

    # Deliberately no location, no service — a SaaS/online business shouldn't
    # be blocked from completing onboarding without them.
    state = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/onboarding", headers=headers).json()
    assert state["ready_to_complete"] is True
    assert state["incomplete_requirements"] == []

    complete_response = db_backed_client.post(f"/api/v1/tenants/{tenant.id}/complete-onboarding", headers=headers)
    assert complete_response.status_code == 200
    assert complete_response.json()["onboarding_status"] == "completed"
    assert complete_response.json()["onboarding_completed_at"] is not None


def test_completed_onboarding_does_not_revert_when_configuration_regresses(
    db_backed_client: TestClient, db_session: Session
):
    """Documented product decision: completion is monotonic. Regressing
    below the minimum bar after completion shows a warning (same
    incomplete_requirements list) but does not un-complete the tenant."""
    seed_industry_templates(db_session)
    tenant, owner, _ = make_tenant_with_owner(db_session)
    headers = _auth_headers(owner)

    _bring_to_minimal_valid_config(db_backed_client, tenant.id, headers)
    complete_response = db_backed_client.post(f"/api/v1/tenants/{tenant.id}/complete-onboarding", headers=headers)
    assert complete_response.status_code == 200

    # Regress: remove the only active FAQ.
    faqs = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/faqs", headers=headers).json()
    db_backed_client.patch(
        f"/api/v1/tenants/{tenant.id}/faqs/{faqs[0]['id']}", json={"is_active": False}, headers=headers
    )

    state = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/onboarding", headers=headers).json()
    assert state["status"] == "completed"  # NOT reverted
    assert state["ready_to_complete"] is False  # but the warning is visible
    assert any(r["code"] == "knowledge_or_faq" for r in state["incomplete_requirements"])

    # Calling complete-onboarding again is a no-op success, not a re-check.
    second_complete = db_backed_client.post(f"/api/v1/tenants/{tenant.id}/complete-onboarding", headers=headers)
    assert second_complete.status_code == 200
    assert second_complete.json()["onboarding_status"] == "completed"


def test_member_cannot_update_business_profile(db_backed_client: TestClient, db_session: Session):
    tenant, _owner, _ = make_tenant_with_owner(db_session)
    member = make_user(db_session)
    add_member(db_session, tenant=tenant, user=member, role=TenantMemberRole.MEMBER)

    response = db_backed_client.patch(
        f"/api/v1/tenants/{tenant.id}/business-profile",
        json={"business_name": "Hijacked"},
        headers=_auth_headers(member),
    )
    assert response.status_code == 403


def test_member_can_read_onboarding_state(db_backed_client: TestClient, db_session: Session):
    tenant, _owner, _ = make_tenant_with_owner(db_session)
    member = make_user(db_session)
    add_member(db_session, tenant=tenant, user=member, role=TenantMemberRole.MEMBER)

    response = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/onboarding", headers=_auth_headers(member))
    assert response.status_code == 200
