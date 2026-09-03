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


class TestActivityFeed:
    def test_empty_by_default(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/activity", headers=_auth_headers(owner))
        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["total"] == 0

    def test_pagination_is_bounded(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/activity", params={"limit": 10_000}, headers=_auth_headers(owner)
        )
        assert response.status_code == 422

    def test_activity_is_tenant_isolated(self, db_backed_client: TestClient, db_session: Session):
        from app.models.contact import Contact
        from app.services import notes_service

        tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="A")
        tenant_b, owner_b, _ = make_tenant_with_owner(db_session, tenant_name="B")
        contact_a = Contact(tenant_id=tenant_a.id, name="A Contact")
        db_session.add(contact_a)
        db_session.flush()

        notes_service.create_note(
            db_session,
            tenant_id=tenant_a.id,
            author_user_id=owner_a.id,
            entity_type="contact",
            entity_id=contact_a.id,
            body="note",
        )
        db_session.commit()

        response_a = db_backed_client.get(f"/api/v1/tenants/{tenant_a.id}/activity", headers=_auth_headers(owner_a))
        response_b = db_backed_client.get(f"/api/v1/tenants/{tenant_b.id}/activity", headers=_auth_headers(owner_b))
        assert response_a.json()["total"] == 1
        assert response_b.json()["total"] == 0

    def test_cross_tenant_access_is_404(self, db_backed_client: TestClient, db_session: Session):
        tenant_a, _, _ = make_tenant_with_owner(db_session, tenant_name="A")
        _, outsider, _ = make_tenant_with_owner(db_session, tenant_name="B")
        response = db_backed_client.get(f"/api/v1/tenants/{tenant_a.id}/activity", headers=_auth_headers(outsider))
        assert response.status_code == 404
