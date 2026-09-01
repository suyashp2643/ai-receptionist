import uuid

from app.config import get_settings
from app.core.security import create_access_token
from app.repositories.tenant_member import TenantMemberScopedRepository
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import make_tenant_with_owner

settings = get_settings()


def _auth_headers_for(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


class TestHttpLevelIsolation:
    """Tenant A's owner attempting anything against Tenant B, over HTTP."""

    def test_cannot_read_other_tenant(self, db_backed_client: TestClient, db_session: Session):
        _tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, _owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")

        response = db_backed_client.get(f"/api/v1/tenants/{tenant_b.id}", headers=_auth_headers_for(owner_a))
        assert response.status_code == 404

    def test_cannot_update_other_tenant(self, db_backed_client: TestClient, db_session: Session):
        _tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, _owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")

        response = db_backed_client.patch(
            f"/api/v1/tenants/{tenant_b.id}",
            json={"name": "Pwned"},
            headers=_auth_headers_for(owner_a),
        )
        assert response.status_code == 404

    def test_cannot_list_other_tenant_members(self, db_backed_client: TestClient, db_session: Session):
        _tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, _owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")

        response = db_backed_client.get(f"/api/v1/tenants/{tenant_b.id}/members", headers=_auth_headers_for(owner_a))
        assert response.status_code == 404

    def test_update_does_not_leak_via_side_channel(self, db_backed_client: TestClient, db_session: Session):
        """A failed cross-tenant update must not have mutated anything."""
        _tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B Original")

        db_backed_client.patch(
            f"/api/v1/tenants/{tenant_b.id}",
            json={"name": "Pwned"},
            headers=_auth_headers_for(owner_a),
        )

        # Owner B's own read must still show the untouched name.
        confirm = db_backed_client.get(f"/api/v1/tenants/{tenant_b.id}", headers=_auth_headers_for(owner_b))
        assert confirm.json()["name"] == "Tenant B Original"


class TestRepositoryLevelIsolation:
    """The tenant-scoped repository itself, independent of any HTTP route."""

    def test_scoped_repository_list_excludes_other_tenants(self, db_session: Session):
        tenant_a, _owner_a, member_a = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        _tenant_b, _owner_b, _member_b = make_tenant_with_owner(db_session, tenant_name="Tenant B")

        repo = TenantMemberScopedRepository(db_session, tenant_a.id)
        results = repo.list()

        assert len(results) == 1
        assert results[0].id == member_a.id

    def test_scoped_repository_get_returns_none_for_other_tenants_resource(self, db_session: Session):
        tenant_a, _owner_a, _member_a = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        _tenant_b, _owner_b, member_b = make_tenant_with_owner(db_session, tenant_name="Tenant B")

        repo = TenantMemberScopedRepository(db_session, tenant_a.id)
        # member_b's id is real, but it belongs to Tenant B — must not resolve
        # under Tenant A's scope.
        assert repo.get(member_b.id) is None

    def test_scoped_repository_delete_refuses_other_tenants_resource(self, db_session: Session):
        tenant_a, _owner_a, _member_a = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        _tenant_b, _owner_b, member_b = make_tenant_with_owner(db_session, tenant_name="Tenant B")

        repo = TenantMemberScopedRepository(db_session, tenant_a.id)
        deleted = repo.delete(member_b.id)

        assert deleted is False
        # member_b must still exist — untouched.
        assert db_session.get(type(member_b), member_b.id) is not None
