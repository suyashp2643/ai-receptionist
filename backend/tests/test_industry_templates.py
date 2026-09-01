import uuid

from app.config import get_settings
from app.core.security import create_access_token
from app.models.industry_template import IndustryTemplate
from app.repositories.industry_template import IndustryTemplateRepository
from app.seed_data.industry_templates import ALL_TEMPLATES
from app.seed_data.seed_runner import seed_industry_templates
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.factories import make_tenant_with_owner, make_user

settings = get_settings()

EXPECTED_KEYS = {
    "real_estate",
    "clinic",
    "hotel",
    "restaurant",
    "automotive",
    "law_firm",
    "education",
    "home_services",
    "saas",
    "custom",
}


def _auth_headers(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


def test_seed_creates_all_ten_templates_and_is_idempotent(db_session: Session):
    first = seed_industry_templates(db_session)
    assert set(k.split(":")[0] for k in first.created) | set(k.split(":")[0] for k in first.skipped) == EXPECTED_KEYS

    second = seed_industry_templates(db_session)
    assert second.created == []
    assert len(second.skipped) == len(ALL_TEMPLATES)


def test_all_templates_present_and_valid(db_session: Session):
    seed_industry_templates(db_session)
    keys = {t.key for t in db_session.scalars(select(IndustryTemplate)).all()}
    assert EXPECTED_KEYS.issubset(keys)

    for template in db_session.scalars(select(IndustryTemplate)).all():
        assert template.default_qualification_schema is not None
        assert isinstance(template.default_actions, list)
        assert template.is_active is True


def test_clinic_and_law_firm_have_mandatory_safety_language(db_session: Session):
    seed_industry_templates(db_session)
    clinic = IndustryTemplateRepository(db_session).get_latest_active_by_key("clinic")
    law_firm = IndustryTemplateRepository(db_session).get_latest_active_by_key("law_firm")

    assert any("diagnose" in rule.lower() for rule in clinic.default_safety_rules)
    assert any("emergency" in rule.lower() for rule in clinic.default_safety_rules)
    assert any("legal advice" in rule.lower() for rule in law_firm.default_safety_rules)


def test_catalog_endpoint_lists_all_templates(db_backed_client: TestClient, db_session: Session):
    seed_industry_templates(db_session)
    user = make_user(db_session)

    response = db_backed_client.get("/api/v1/industry-templates", headers=_auth_headers(user))
    assert response.status_code == 200
    keys = {t["key"] for t in response.json()}
    assert EXPECTED_KEYS.issubset(keys)


def test_get_single_template_by_key(db_backed_client: TestClient, db_session: Session):
    seed_industry_templates(db_session)
    user = make_user(db_session)

    response = db_backed_client.get("/api/v1/industry-templates/real_estate", headers=_auth_headers(user))
    assert response.status_code == 200
    body = response.json()
    assert body["key"] == "real_estate"
    assert "default_qualification_schema" in body


def test_unknown_template_key_returns_404(db_backed_client: TestClient, db_session: Session):
    user = make_user(db_session)
    response = db_backed_client.get("/api/v1/industry-templates/does-not-exist", headers=_auth_headers(user))
    assert response.status_code == 404


def test_unauthenticated_cannot_view_catalog(db_backed_client: TestClient):
    response = db_backed_client.get("/api/v1/industry-templates")
    assert response.status_code == 401


def test_no_api_route_exists_to_mutate_templates(db_backed_client: TestClient, db_session: Session):
    """There is deliberately no POST/PATCH/DELETE route for industry templates
    at all — this documents that absence as a real, tested guarantee rather
    than an assumption."""
    user = make_user(db_session)
    headers = _auth_headers(user)
    assert db_backed_client.post("/api/v1/industry-templates", json={}, headers=headers).status_code == 405
    assert db_backed_client.patch("/api/v1/industry-templates/real_estate", json={}, headers=headers).status_code == 405


def test_selecting_template_creates_tenant_owned_snapshot(db_backed_client: TestClient, db_session: Session):
    seed_industry_templates(db_session)
    tenant, owner, _ = make_tenant_with_owner(db_session)

    response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/select-industry",
        json={"template_key": "clinic"},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 200
    assert response.json()["industry_template_id"] is not None

    receptionists = db_backed_client.get(
        f"/api/v1/tenants/{tenant.id}/receptionists", headers=_auth_headers(owner)
    ).json()
    assert len(receptionists) == 1
    workflow = db_backed_client.get(
        f"/api/v1/tenants/{tenant.id}/receptionists/{receptionists[0]['id']}/workflow",
        headers=_auth_headers(owner),
    ).json()
    assert len(workflow["qualification_schema"]["fields"]) > 0
    assert "request_appointment" in workflow["enabled_actions"]


def test_tenant_customization_does_not_mutate_global_template(db_backed_client: TestClient, db_session: Session):
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

    original_template = IndustryTemplateRepository(db_session).get_latest_active_by_key("clinic")
    original_field_count = len(original_template.default_qualification_schema["fields"])

    # Tenant heavily customizes their qualification schema.
    db_backed_client.patch(
        f"/api/v1/tenants/{tenant.id}/receptionists/{receptionist_id}/workflow",
        json={"qualification_schema": {"fields": []}},
        headers=_auth_headers(owner),
    )

    reloaded_template = IndustryTemplateRepository(db_session).get_latest_active_by_key("clinic")
    assert len(reloaded_template.default_qualification_schema["fields"]) == original_field_count
