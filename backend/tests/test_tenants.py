import uuid

from app.config import get_settings
from app.core.security import create_access_token
from app.models.enums import TenantMemberRole
from app.models.user import User
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import add_member, make_tenant, make_tenant_with_owner, make_user

settings = get_settings()


def _token_for(user: User) -> str:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return token


def _auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token_for(user)}"}


def test_owner_can_read_and_update_tenant(db_backed_client: TestClient, db_session: Session):
    tenant, owner, _member = make_tenant_with_owner(db_session)

    read_response = db_backed_client.get(
        f"/api/v1/tenants/{tenant.id}", headers=_auth_headers(owner)
    )
    assert read_response.status_code == 200
    assert read_response.json()["my_role"] == "owner"

    update_response = db_backed_client.patch(
        f"/api/v1/tenants/{tenant.id}",
        json={"name": "Renamed Workspace"},
        headers=_auth_headers(owner),
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Renamed Workspace"


def test_admin_can_read_and_update_but_not_more_than_owner(
    db_backed_client: TestClient, db_session: Session
):
    tenant, _owner, _ = make_tenant_with_owner(db_session)
    admin_user = make_user(db_session)
    add_member(db_session, tenant=tenant, user=admin_user, role=TenantMemberRole.ADMIN)

    update_response = db_backed_client.patch(
        f"/api/v1/tenants/{tenant.id}",
        json={"name": "Admin Renamed"},
        headers=_auth_headers(admin_user),
    )
    assert update_response.status_code == 200

    members_response = db_backed_client.get(
        f"/api/v1/tenants/{tenant.id}/members", headers=_auth_headers(admin_user)
    )
    assert members_response.status_code == 200
    assert len(members_response.json()) == 2  # owner + this admin


def test_member_can_read_but_not_update_tenant(db_backed_client: TestClient, db_session: Session):
    tenant, _owner, _ = make_tenant_with_owner(db_session)
    member_user = make_user(db_session)
    add_member(db_session, tenant=tenant, user=member_user, role=TenantMemberRole.MEMBER)

    read_response = db_backed_client.get(
        f"/api/v1/tenants/{tenant.id}", headers=_auth_headers(member_user)
    )
    assert read_response.status_code == 200
    assert read_response.json()["my_role"] == "member"

    update_response = db_backed_client.patch(
        f"/api/v1/tenants/{tenant.id}",
        json={"name": "Should Not Work"},
        headers=_auth_headers(member_user),
    )
    assert update_response.status_code == 403


def test_member_cannot_list_tenant_members(db_backed_client: TestClient, db_session: Session):
    tenant, _owner, _ = make_tenant_with_owner(db_session)
    member_user = make_user(db_session)
    add_member(db_session, tenant=tenant, user=member_user, role=TenantMemberRole.MEMBER)

    response = db_backed_client.get(
        f"/api/v1/tenants/{tenant.id}/members", headers=_auth_headers(member_user)
    )
    assert response.status_code == 403


def test_unauthenticated_request_rejected(db_backed_client: TestClient, db_session: Session):
    tenant = make_tenant(db_session)
    response = db_backed_client.get(f"/api/v1/tenants/{tenant.id}")
    assert response.status_code == 401


def test_non_member_cannot_access_tenant(db_backed_client: TestClient, db_session: Session):
    tenant = make_tenant(db_session)
    outsider = make_user(db_session)

    response = db_backed_client.get(f"/api/v1/tenants/{tenant.id}", headers=_auth_headers(outsider))
    assert response.status_code == 404


def test_client_supplied_role_cannot_elevate_privileges(
    db_backed_client: TestClient, db_session: Session
):
    """The role in the DB is the only source of truth — a member trying to
    smuggle a higher role into the request body must have no effect."""
    tenant, _owner, _ = make_tenant_with_owner(db_session)
    member_user = make_user(db_session)
    add_member(db_session, tenant=tenant, user=member_user, role=TenantMemberRole.MEMBER)

    response = db_backed_client.patch(
        f"/api/v1/tenants/{tenant.id}",
        json={"name": "Hijacked", "role": "owner", "my_role": "owner"},
        headers=_auth_headers(member_user),
    )
    assert response.status_code == 403


def test_create_tenant_endpoint_creates_owner_membership(
    db_backed_client: TestClient, db_session: Session
):
    user = make_user(db_session)
    response = db_backed_client.post(
        "/api/v1/tenants",
        json={"name": "New Workspace", "timezone": "UTC"},
        headers=_auth_headers(user),
    )
    assert response.status_code == 201
    assert response.json()["my_role"] == "owner"


def test_list_my_tenants_only_shows_own_memberships(
    db_backed_client: TestClient, db_session: Session
):
    tenant_a, user, _ = make_tenant_with_owner(db_session, tenant_name="Mine")
    make_tenant_with_owner(db_session, tenant_name="Not Mine")  # another user's tenant

    response = db_backed_client.get("/api/v1/tenants", headers=_auth_headers(user))
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["tenant_id"] == str(tenant_a.id)
