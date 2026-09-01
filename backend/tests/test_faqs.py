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


def test_create_faq(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/faqs",
        json={"question": "What are your hours?", "answer": "9am to 5pm, Monday to Friday."},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 201
    assert response.json()["possible_duplicate_of"] is None


def test_duplicate_question_flagged_but_not_blocked(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    headers = _auth_headers(owner)
    db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/faqs",
        json={"question": "What are your hours?", "answer": "9am to 5pm."},
        headers=headers,
    )
    response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/faqs",
        json={"question": "  WHAT ARE   your hours?  ", "answer": "Different answer."},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["possible_duplicate_of"] is not None


def test_html_rejected_in_question_and_answer(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/faqs",
        json={"question": "<script>alert(1)</script>", "answer": "Safe answer"},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 422


def test_question_length_limit_enforced(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    response = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/faqs",
        json={"question": "x" * 501, "answer": "Answer"},
        headers=_auth_headers(owner),
    )
    assert response.status_code == 422


def test_member_cannot_delete_faq(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _ = make_tenant_with_owner(db_session)
    member = make_user(db_session)
    add_member(db_session, tenant=tenant, user=member, role=TenantMemberRole.MEMBER)

    faq = db_backed_client.post(
        f"/api/v1/tenants/{tenant.id}/faqs",
        json={"question": "Q?", "answer": "A."},
        headers=_auth_headers(owner),
    ).json()["faq"]

    response = db_backed_client.delete(f"/api/v1/tenants/{tenant.id}/faqs/{faq['id']}", headers=_auth_headers(member))
    assert response.status_code == 403
