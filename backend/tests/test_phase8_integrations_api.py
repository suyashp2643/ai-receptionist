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


def _create_mock_connection(client: TestClient, *, tenant_id, headers, name="Test Mock", event_types=None):
    return client.post(
        f"/api/v1/tenants/{tenant_id}/integrations",
        headers=headers,
        json={
            "connector_type": "mock",
            "name": name,
            "config": {"mode": "success"},
            "enabled_event_types": event_types or ["contact.captured"],
        },
    )


class TestPermissionMatrix:
    def test_unauthenticated_gets_401(self, db_backed_client: TestClient, db_session: Session):
        tenant, _owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/integrations")
        assert response.status_code == 401

    def test_non_member_gets_404(self, db_backed_client: TestClient, db_session: Session):
        tenant, _owner, _ = make_tenant_with_owner(db_session)
        outsider = make_user(db_session)
        response = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/integrations", headers=_auth_headers(outsider))
        assert response.status_code == 404

    def test_member_can_list_but_not_create(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        member = make_user(db_session)
        add_member(db_session, tenant=tenant, user=member, role=TenantMemberRole.MEMBER)

        list_response = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/integrations", headers=_auth_headers(member))
        assert list_response.status_code == 200

        create_response = _create_mock_connection(db_backed_client, tenant_id=tenant.id, headers=_auth_headers(member))
        assert create_response.status_code == 403

    def test_owner_can_create(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        response = _create_mock_connection(db_backed_client, tenant_id=tenant.id, headers=_auth_headers(owner))
        assert response.status_code == 201

    def test_a_real_connection_id_from_another_tenant_is_still_404(
        self, db_backed_client: TestClient, db_session: Session
    ):
        """Phase 9 audit finding: prior coverage only proved a non-member of
        Tenant B gets 404 at the tenant level — this proves the stronger,
        more realistic IDOR case: a genuine member of Tenant A, using
        Tenant A's own URL and their own valid membership, cannot reach
        Tenant B's connection by guessing/reusing its real connection_id."""
        tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, owner_b, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        create_response = _create_mock_connection(
            db_backed_client, tenant_id=tenant_b.id, headers=_auth_headers(owner_b)
        )
        assert create_response.status_code == 201
        connection_id = create_response.json()["id"]
        headers_a = _auth_headers(owner_a)

        get_response = db_backed_client.get(
            f"/api/v1/tenants/{tenant_a.id}/integrations/{connection_id}", headers=headers_a
        )
        assert get_response.status_code == 404

        put_response = db_backed_client.put(
            f"/api/v1/tenants/{tenant_a.id}/integrations/{connection_id}",
            headers=headers_a,
            json={"config": {"mode": "success"}, "enabled_event_types": [], "expected_version": 1},
        )
        assert put_response.status_code == 404

        pause_response = db_backed_client.post(
            f"/api/v1/tenants/{tenant_a.id}/integrations/{connection_id}/pause",
            headers=headers_a,
            json={"expected_version": 1},
        )
        assert pause_response.status_code == 404

        deliveries_response = db_backed_client.get(
            f"/api/v1/tenants/{tenant_a.id}/integrations/{connection_id}/deliveries", headers=headers_a
        )
        assert deliveries_response.status_code == 404

        rotate_response = db_backed_client.post(
            f"/api/v1/tenants/{tenant_a.id}/integrations/{connection_id}/rotate-secret",
            headers=headers_a,
            json={"new_secret": "irrelevant-since-this-must-404-first", "expected_version": 1},
        )
        assert rotate_response.status_code == 404

        # Confirm Tenant B's connection actually still exists, untouched, under its own tenant.
        still_there = db_backed_client.get(
            f"/api/v1/tenants/{tenant_b.id}/integrations/{connection_id}", headers=_auth_headers(owner_b)
        )
        assert still_there.status_code == 200
        assert still_there.json()["name"] == "Test Mock"


class TestConnectionLifecycle:
    def test_full_lifecycle(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        headers = _auth_headers(owner)

        created = _create_mock_connection(db_backed_client, tenant_id=tenant.id, headers=headers)
        assert created.status_code == 201
        body = created.json()
        connection_id = body["id"]
        assert body["status"] == "configured"
        assert body["has_signing_secret"] is False
        version = body["version"]

        detail = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}", headers=headers)
        assert detail.status_code == 200

        verify = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}/verify", headers=headers
        )
        assert verify.status_code == 200
        assert verify.json()["success"] is True

        detail = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}", headers=headers)
        assert detail.json()["status"] == "verified"
        version = detail.json()["version"]

        test_event = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}/test-event", headers=headers
        )
        assert test_event.status_code == 200
        assert test_event.json()["event_type"] == "connection.test_event"

        deliveries = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}/deliveries", headers=headers
        )
        assert deliveries.status_code == 200
        assert deliveries.json()["total"] >= 1

        pause = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}/pause",
            headers=headers,
            json={"expected_version": version},
        )
        assert pause.status_code == 200
        assert pause.json()["status"] == "paused"
        version = pause.json()["version"]

        # Stale version must be rejected with 409, never silently applied.
        stale_resume = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}/resume",
            headers=headers,
            json={"expected_version": version - 1},
        )
        assert stale_resume.status_code == 409

        resume = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}/resume",
            headers=headers,
            json={"expected_version": version},
        )
        assert resume.status_code == 200
        assert resume.json()["status"] == "configured"
        version = resume.json()["version"]

        disable = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}/disable",
            headers=headers,
            json={"expected_version": version},
        )
        assert disable.status_code == 200
        assert disable.json()["status"] == "disabled"

    def test_duplicate_name_is_rejected(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        headers = _auth_headers(owner)
        first = _create_mock_connection(db_backed_client, tenant_id=tenant.id, headers=headers, name="Same Name")
        assert first.status_code == 201
        second = _create_mock_connection(db_backed_client, tenant_id=tenant.id, headers=headers, name="Same Name")
        assert second.status_code == 422

    def test_unrecognized_connector_type_is_rejected(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations",
            headers=_auth_headers(owner),
            json={"connector_type": "not_a_real_connector", "name": "X", "config": {}, "enabled_event_types": []},
        )
        assert response.status_code == 422

    def test_unrecognized_event_type_is_rejected(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations",
            headers=_auth_headers(owner),
            json={
                "connector_type": "mock",
                "name": "X",
                "config": {},
                "enabled_event_types": ["not.a.real.event"],
            },
        )
        assert response.status_code == 422

    def test_webhook_without_signing_secret_is_rejected(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations",
            headers=_auth_headers(owner),
            json={
                "connector_type": "webhook",
                "name": "Webhook",
                "config": {"destination_url": "http://127.0.0.1:9999/hook"},
                "enabled_event_types": [],
            },
        )
        assert response.status_code == 422

    def test_sales_employee_rejects_safety_escalation_subscription(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations",
            headers=_auth_headers(owner),
            json={
                "connector_type": "sales_employee",
                "name": "Sales Employee",
                "config": {"destination_url": "http://127.0.0.1:9999/hook"},
                "enabled_event_types": ["safety.escalation_detected"],
                "signing_secret": "a-real-secret",
            },
        )
        assert response.status_code == 422


class TestProcessPendingNow:
    """The route's real claim/deliver behavior against genuinely committed
    data is covered end-to-end by
    tests/integration/test_phase8_outbox_worker.py (it must run through a
    real, separate DB connection — outbox_worker_service always opens its
    own session_scope(), which cannot see this test's uncommitted
    savepoint). This class only proves the route is reachable, permission-
    gated, and returns the expected shape."""

    def test_owner_can_call_it_and_gets_a_valid_shape(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        headers = _auth_headers(owner)
        created = _create_mock_connection(db_backed_client, tenant_id=tenant.id, headers=headers)
        connection_id = created.json()["id"]

        response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}/process-pending", headers=headers
        )
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == {"claimed", "delivered", "retried", "dead_lettered"}

    def test_member_cannot_call_it(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        headers = _auth_headers(owner)
        created = _create_mock_connection(db_backed_client, tenant_id=tenant.id, headers=headers)
        connection_id = created.json()["id"]

        member = make_user(db_session)
        add_member(db_session, tenant=tenant, user=member, role=TenantMemberRole.MEMBER)
        response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}/process-pending", headers=_auth_headers(member)
        )
        assert response.status_code == 403


class TestFieldMappingPreview:
    def test_previews_a_mapping_against_fictional_sample_data(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        headers = _auth_headers(owner)
        created = _create_mock_connection(db_backed_client, tenant_id=tenant.id, headers=headers)
        connection_id = created.json()["id"]

        response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}/preview-mapping",
            headers=headers,
            json={
                "sample_data": {"phone": "555-0100", "internal_id": "abc"},
                "field_mapping": {"rename": {"phone": "phone_number"}, "omit": ["internal_id"]},
            },
        )
        assert response.status_code == 200
        assert response.json()["result"] == {"phone_number": "555-0100"}

    def test_an_invalid_mapping_is_422(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        headers = _auth_headers(owner)
        created = _create_mock_connection(db_backed_client, tenant_id=tenant.id, headers=headers)
        connection_id = created.json()["id"]

        response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}/preview-mapping",
            headers=headers,
            json={"sample_data": {}, "field_mapping": {"not_a_real_key": True}},
        )
        assert response.status_code == 422

    def test_member_can_preview_a_mapping(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        headers = _auth_headers(owner)
        created = _create_mock_connection(db_backed_client, tenant_id=tenant.id, headers=headers)
        connection_id = created.json()["id"]

        member = make_user(db_session)
        add_member(db_session, tenant=tenant, user=member, role=TenantMemberRole.MEMBER)
        response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}/preview-mapping",
            headers=_auth_headers(member),
            json={"sample_data": {"a": 1}, "field_mapping": {}},
        )
        assert response.status_code == 200


class TestInboundApiKey:
    def test_key_is_returned_exactly_once_and_never_again(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        headers = _auth_headers(owner)
        created = _create_mock_connection(db_backed_client, tenant_id=tenant.id, headers=headers)
        connection_id = created.json()["id"]
        version = created.json()["version"]

        key_response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}/inbound-key",
            headers=headers,
            json={"expected_version": version},
        )
        assert key_response.status_code == 200
        body = key_response.json()
        assert body["api_key"].startswith(settings.integration_api_key_prefix)
        assert body["last_four"] == body["api_key"][-4:]

        detail = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/integrations/{connection_id}", headers=headers)
        detail_body = detail.json()
        assert "api_key" not in detail_body
        assert detail_body["inbound_api_key_last_four"] == body["last_four"]
        # Confirm the raw key never appears anywhere in the detail response.
        assert body["api_key"] not in str(detail_body)
