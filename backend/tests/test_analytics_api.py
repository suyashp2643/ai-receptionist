"""HTTP-level auth/tenant-isolation coverage for the analytics routes.

tests/test_analytics_service.py already exercises `analytics_service`'s
functions directly — thoroughly, but bypassing `get_tenant_context`
entirely, so it proves nothing about the route layer's own auth/tenant
checks. Phase 9 audit finding: this left `/tenants/{tenant_id}/analytics/*`
with zero regression coverage for non-member/cross-tenant access at the
HTTP boundary. This file closes that gap; it does not duplicate the
service-level aggregation-correctness tests."""

import uuid

from app.config import get_settings
from app.core.security import create_access_token
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import make_tenant_with_owner, make_user

settings = get_settings()


def _auth_headers(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


class TestAnalyticsOverviewAuth:
    def test_member_can_view_overview(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/analytics/overview", headers=_auth_headers(owner))
        assert response.status_code == 200

    def test_unauthenticated_gets_401(self, db_backed_client: TestClient, db_session: Session):
        tenant, _owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/analytics/overview")
        assert response.status_code == 401

    def test_non_member_gets_404_not_403(self, db_backed_client: TestClient, db_session: Session):
        tenant, _owner, _ = make_tenant_with_owner(db_session)
        outsider = make_user(db_session)
        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/analytics/overview", headers=_auth_headers(outsider)
        )
        assert response.status_code == 404


class TestAnalyticsTimeseriesAuth:
    def test_member_can_view_timeseries(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/analytics/timeseries", headers=_auth_headers(owner)
        )
        assert response.status_code == 200

    def test_unauthenticated_gets_401(self, db_backed_client: TestClient, db_session: Session):
        tenant, _owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/analytics/timeseries")
        assert response.status_code == 401

    def test_non_member_gets_404_not_403(self, db_backed_client: TestClient, db_session: Session):
        tenant, _owner, _ = make_tenant_with_owner(db_session)
        outsider = make_user(db_session)
        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/analytics/timeseries", headers=_auth_headers(outsider)
        )
        assert response.status_code == 404

    def test_invalid_custom_range_is_422(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/analytics/timeseries",
            params={"preset": "custom", "custom_start": "2026-01-01", "custom_end": "2020-01-01"},
            headers=_auth_headers(owner),
        )
        assert response.status_code == 422
