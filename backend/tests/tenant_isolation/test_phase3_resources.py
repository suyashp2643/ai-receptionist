import uuid

from app.config import get_settings
from app.core.security import create_access_token
from app.models.business_location import BusinessLocation
from app.models.faq import FAQ
from app.models.service import Service
from app.repositories.business_location import BusinessLocationRepository
from app.repositories.faq import FAQRepository
from app.repositories.receptionist import ReceptionistRepository, ReceptionistWorkflowRepository
from app.repositories.service import ServiceRepository
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import make_receptionist, make_tenant_with_owner

settings = get_settings()


def _auth_headers_for(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


class TestHttpLevelIsolation:
    def test_cannot_read_other_tenants_receptionist(self, db_backed_client: TestClient, db_session: Session):
        _tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, _owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        receptionist_b, _ = make_receptionist(db_session, tenant=tenant_b)

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant_b.id}/receptionists/{receptionist_b.id}",
            headers=_auth_headers_for(owner_a),
        )
        assert response.status_code == 404

    def test_cannot_update_other_tenants_receptionist(self, db_backed_client: TestClient, db_session: Session):
        _tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, _owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        receptionist_b, _ = make_receptionist(db_session, tenant=tenant_b)

        response = db_backed_client.patch(
            f"/api/v1/tenants/{tenant_b.id}/receptionists/{receptionist_b.id}",
            json={"name": "Pwned"},
            headers=_auth_headers_for(owner_a),
        )
        assert response.status_code == 404

    def test_cannot_read_other_tenants_workflow(self, db_backed_client: TestClient, db_session: Session):
        _tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, _owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        receptionist_b, _workflow_b = make_receptionist(db_session, tenant=tenant_b)

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant_b.id}/receptionists/{receptionist_b.id}/workflow",
            headers=_auth_headers_for(owner_a),
        )
        assert response.status_code == 404

    def test_cannot_access_other_tenants_locations(self, db_backed_client: TestClient, db_session: Session):
        _tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        location_b = db_backed_client.post(
            f"/api/v1/tenants/{tenant_b.id}/locations",
            json={"name": "Tenant B HQ"},
            headers=_auth_headers_for(owner_b),
        ).json()

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant_b.id}/locations/{location_b['id']}", headers=_auth_headers_for(owner_a)
        )
        assert response.status_code == 404

    def test_cannot_access_other_tenants_services(self, db_backed_client: TestClient, db_session: Session):
        _tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        service_b = db_backed_client.post(
            f"/api/v1/tenants/{tenant_b.id}/services",
            json={"name": "Tenant B Service"},
            headers=_auth_headers_for(owner_b),
        ).json()

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant_b.id}/services/{service_b['id']}", headers=_auth_headers_for(owner_a)
        )
        assert response.status_code == 404

    def test_cannot_access_other_tenants_faqs(self, db_backed_client: TestClient, db_session: Session):
        _tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        faq_b = db_backed_client.post(
            f"/api/v1/tenants/{tenant_b.id}/faqs",
            json={"question": "B question?", "answer": "B answer."},
            headers=_auth_headers_for(owner_b),
        ).json()["faq"]

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant_b.id}/faqs/{faq_b['id']}", headers=_auth_headers_for(owner_a)
        )
        assert response.status_code == 404

    def test_cannot_access_other_tenants_knowledge(self, db_backed_client: TestClient, db_session: Session):
        _tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        source_b = db_backed_client.post(
            f"/api/v1/tenants/{tenant_b.id}/knowledge/sources",
            json={"type": "manual", "title": "B Source"},
            headers=_auth_headers_for(owner_b),
        ).json()
        document_b = db_backed_client.post(
            f"/api/v1/tenants/{tenant_b.id}/knowledge/documents",
            json={"source_id": source_b["id"], "title": "B Doc", "raw_text": "Tenant B private content."},
            headers=_auth_headers_for(owner_b),
        ).json()

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant_b.id}/knowledge/documents/{document_b['id']}",
            headers=_auth_headers_for(owner_a),
        )
        assert response.status_code == 404

    def test_cannot_create_resource_under_other_tenant_via_path(
        self, db_backed_client: TestClient, db_session: Session
    ):
        """Even with a valid membership elsewhere, POSTing into another
        tenant's URL must fail — not silently create data owned by tenant A
        under tenant B's id, and not succeed at all."""
        _tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, _owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")

        response = db_backed_client.post(
            f"/api/v1/tenants/{tenant_b.id}/faqs",
            json={"question": "Hijack?", "answer": "Hijack."},
            headers=_auth_headers_for(owner_a),
        )
        assert response.status_code == 404


class TestRepositoryLevelIsolation:
    def test_receptionist_repository_excludes_other_tenants(self, db_session: Session):
        tenant_a, _owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, _owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        receptionist_b, _ = make_receptionist(db_session, tenant=tenant_b)

        repo = ReceptionistRepository(db_session, tenant_a.id)
        assert repo.get(receptionist_b.id) is None
        assert repo.list_ordered() == []

    def test_workflow_repository_excludes_other_tenants(self, db_session: Session):
        tenant_a, _owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, _owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        receptionist_b, workflow_b = make_receptionist(db_session, tenant=tenant_b)

        repo = ReceptionistWorkflowRepository(db_session, tenant_a.id)
        assert repo.get(workflow_b.id) is None
        assert repo.get_by_receptionist_id(receptionist_b.id) is None

    def test_location_repository_excludes_other_tenants(self, db_session: Session):
        tenant_a, _owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, _owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        location_b = BusinessLocation(tenant_id=tenant_b.id, name="B Office")
        db_session.add(location_b)
        db_session.flush()

        repo = BusinessLocationRepository(db_session, tenant_a.id)
        assert repo.get(location_b.id) is None
        assert repo.delete(location_b.id) is False
        assert db_session.get(BusinessLocation, location_b.id) is not None  # untouched

    def test_service_repository_excludes_other_tenants(self, db_session: Session):
        tenant_a, _owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, _owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        service_b = Service(tenant_id=tenant_b.id, name="B Service")
        db_session.add(service_b)
        db_session.flush()

        repo = ServiceRepository(db_session, tenant_a.id)
        assert repo.get(service_b.id) is None

    def test_faq_repository_excludes_other_tenants(self, db_session: Session):
        tenant_a, _owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, _owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        faq_b = FAQ(tenant_id=tenant_b.id, question="Q?", answer="A.")
        db_session.add(faq_b)
        db_session.flush()

        repo = FAQRepository(db_session, tenant_a.id)
        assert repo.get(faq_b.id) is None
        assert repo.list_ordered() == []
