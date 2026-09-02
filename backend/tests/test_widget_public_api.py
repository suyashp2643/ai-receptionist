import json
import uuid

from app.config import get_settings
from app.core.rate_limit import get_rate_limiter
from app.core.security import create_access_token
from app.models.business_location import BusinessLocation
from app.models.enums import ReceptionistStatus, WidgetInstallationStatus
from app.models.service import Service
from app.models.widget_installation import WidgetInstallation
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import make_receptionist, make_tenant_with_owner

settings = get_settings()


def _auth_headers(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


def _active_receptionist(db_session: Session, tenant):
    receptionist, workflow = make_receptionist(db_session, tenant=tenant)
    receptionist.status = ReceptionistStatus.ACTIVE
    db_session.flush()
    return receptionist, workflow


def _active_installation(db_session: Session, tenant, receptionist, *, allowed_domains=None) -> WidgetInstallation:
    installation = WidgetInstallation(
        tenant_id=tenant.id,
        receptionist_id=receptionist.id,
        allowed_domains=allowed_domains if allowed_domains is not None else ["example.com"],
    )
    installation.status = WidgetInstallationStatus.ACTIVE
    db_session.add(installation)
    db_session.flush()
    return installation


def _parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:") :].strip())
        if event_name is not None:
            events.append({"event": event_name, "data": data})
    return events


def setup_function(_):
    get_rate_limiter().reset()


class TestWidgetConfig:
    def test_config_exposes_only_safe_fields(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)

        response = db_backed_client.get(f"/api/v1/widget/{installation.public_id}/config")
        assert response.status_code == 200
        body = response.json()

        assert body["mock_mode"] is True
        assert "ai_disclosure" in body
        assert body["receptionist_name"] == receptionist.name
        forbidden_keys = {
            "tenant_id",
            "receptionist_id",
            "system_prompt",
            "safety_rules",
            "api_key",
            "internal_id",
        }
        assert forbidden_keys.isdisjoint(body.keys())

    def test_unknown_public_id_is_404(self, db_backed_client: TestClient, db_session: Session):
        response = db_backed_client.get(f"/api/v1/widget/{uuid.uuid4().hex}/config")
        assert response.status_code == 404

    def test_revoked_installation_is_404(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)
        installation.status = WidgetInstallationStatus.REVOKED
        db_session.flush()

        response = db_backed_client.get(f"/api/v1/widget/{installation.public_id}/config")
        assert response.status_code == 404

    def test_disallowed_origin_is_rejected(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist, allowed_domains=["example.com"])

        response = db_backed_client.get(
            f"/api/v1/widget/{installation.public_id}/config", headers={"Origin": "https://evil.com"}
        )
        assert response.status_code == 403

    def test_allowed_origin_is_accepted(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist, allowed_domains=["example.com"])

        response = db_backed_client.get(
            f"/api/v1/widget/{installation.public_id}/config", headers={"Origin": "https://example.com"}
        )
        assert response.status_code == 200

    def test_missing_origin_is_allowed_through(self, db_backed_client: TestClient, db_session: Session):
        """Documented limitation: Origin is abuse reduction, not authentication."""
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist, allowed_domains=["example.com"])

        response = db_backed_client.get(f"/api/v1/widget/{installation.public_id}/config")
        assert response.status_code == 200

    def test_malformed_origin_is_rejected(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist, allowed_domains=["example.com"])

        response = db_backed_client.get(
            f"/api/v1/widget/{installation.public_id}/config", headers={"Origin": "not-a-valid-origin"}
        )
        assert response.status_code == 403

    def test_platform_preview_origin_is_always_allowed(self, db_backed_client: TestClient, db_session: Session):
        """The dashboard's own origin must work for the live preview
        feature regardless of a tenant's configured allowed_domains — and
        without that origin ever being added to allowed_domains itself."""
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist, allowed_domains=["example.com"])
        preview_origin = settings.platform_preview_origins_list[0]

        response = db_backed_client.get(
            f"/api/v1/widget/{installation.public_id}/config", headers={"Origin": preview_origin}
        )
        assert response.status_code == 200
        assert preview_origin not in installation.allowed_domains

    def test_config_lists_only_active_services_and_locations_with_safe_fields(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)

        active_service = Service(tenant_id=tenant.id, name="Consultation", description="A chat with an agent.")
        inactive_service = Service(tenant_id=tenant.id, name="Retired", is_active=False)
        active_location = BusinessLocation(tenant_id=tenant.id, name="Downtown", timezone="America/New_York")
        inactive_location = BusinessLocation(
            tenant_id=tenant.id, name="Closed Branch", timezone="UTC", is_active=False
        )
        db_session.add_all([active_service, inactive_service, active_location, inactive_location])
        db_session.flush()

        response = db_backed_client.get(f"/api/v1/widget/{installation.public_id}/config")
        assert response.status_code == 200
        body = response.json()

        assert [s["name"] for s in body["services"]] == ["Consultation"]
        assert body["services"][0] == {
            "id": str(active_service.id),
            "name": "Consultation",
            "description": "A chat with an agent.",
        }
        assert [loc["name"] for loc in body["locations"]] == ["Downtown"]
        assert body["locations"][0] == {
            "id": str(active_location.id),
            "name": "Downtown",
            "timezone": "America/New_York",
        }

    def test_config_lists_are_empty_when_no_services_or_locations_are_configured(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)

        response = db_backed_client.get(f"/api/v1/widget/{installation.public_id}/config")
        assert response.status_code == 200
        assert response.json()["services"] == []
        assert response.json()["locations"] == []


class TestWidgetSessionsAndConversation:
    def _start_session(self, db_backed_client: TestClient, installation: WidgetInstallation):
        return db_backed_client.post(f"/api/v1/widget/{installation.public_id}/sessions", json={})

    def test_start_session_issues_token_and_conversation(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)

        response = self._start_session(db_backed_client, installation)
        assert response.status_code == 201
        body = response.json()
        assert body["capability_token"]
        assert body["conversation"]["status"] == "active"
        assert "tenant_id" not in body["conversation"]
        assert "receptionist_id" not in body["conversation"]

    def test_paused_installation_rejects_new_sessions(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)
        installation.status = WidgetInstallationStatus.PAUSED
        db_session.flush()

        response = self._start_session(db_backed_client, installation)
        assert response.status_code == 409

    def test_message_send_and_transcript_resume(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)

        session_response = self._start_session(db_backed_client, installation)
        token = session_response.json()["capability_token"]
        conversation_id = session_response.json()["conversation"]["id"]
        headers = {"X-Widget-Session-Token": token}

        msg_response = db_backed_client.post(
            f"/api/v1/widget/{installation.public_id}/conversations/{conversation_id}/messages",
            json={"content": "Hello there"},
            headers=headers,
        )
        assert msg_response.status_code == 200
        events = _parse_sse(msg_response.text)
        assert any(e["event"] == "response.completed" for e in events)

        get_response = db_backed_client.get(
            f"/api/v1/widget/{installation.public_id}/conversations/{conversation_id}", headers=headers
        )
        assert get_response.status_code == 200
        body = get_response.json()
        roles = [m["role"] for m in body["messages"]]
        assert "user" in roles and "assistant" in roles
        assert all(role in ("user", "assistant") for role in roles)

    def test_wrong_conversation_token_is_rejected(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)

        session_a = self._start_session(db_backed_client, installation).json()
        session_b = self._start_session(db_backed_client, installation).json()

        # Token from session B must not read session A's conversation.
        response = db_backed_client.get(
            f"/api/v1/widget/{installation.public_id}/conversations/{session_a['conversation']['id']}",
            headers={"X-Widget-Session-Token": session_b["capability_token"]},
        )
        assert response.status_code == 401

    def test_missing_token_is_rejected(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)
        session = self._start_session(db_backed_client, installation).json()

        response = db_backed_client.get(
            f"/api/v1/widget/{installation.public_id}/conversations/{session['conversation']['id']}"
        )
        assert response.status_code == 401

    def test_cross_tenant_token_cannot_read_other_installation(self, db_backed_client: TestClient, db_session: Session):
        tenant_a, _, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        receptionist_a, _ = _active_receptionist(db_session, tenant_a)
        installation_a = _active_installation(db_session, tenant_a, receptionist_a)

        tenant_b, _, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        receptionist_b, _ = _active_receptionist(db_session, tenant_b)
        installation_b = _active_installation(db_session, tenant_b, receptionist_b)

        session_a = self._start_session(db_backed_client, installation_a).json()

        response = db_backed_client.get(
            f"/api/v1/widget/{installation_b.public_id}/conversations/{session_a['conversation']['id']}",
            headers={"X-Widget-Session-Token": session_a["capability_token"]},
        )
        assert response.status_code == 401


class TestWidgetContactsAppointmentsHandoffs:
    def _session_headers(self, db_backed_client: TestClient, installation: WidgetInstallation) -> dict[str, str]:
        session = db_backed_client.post(f"/api/v1/widget/{installation.public_id}/sessions", json={}).json()
        return {"X-Widget-Session-Token": session["capability_token"]}

    def test_capture_contact_without_marketing_consent(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)
        headers = self._session_headers(db_backed_client, installation)

        response = db_backed_client.post(
            f"/api/v1/widget/{installation.public_id}/contacts",
            json={"name": "Jane Visitor", "email": "jane@example.com"},
            headers=headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["marketing_consent"] is False

    def test_contact_requires_at_least_one_field(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)
        headers = self._session_headers(db_backed_client, installation)

        response = db_backed_client.post(
            f"/api/v1/widget/{installation.public_id}/contacts", json={}, headers=headers
        )
        assert response.status_code == 422

    def test_appointment_request_is_pending_not_confirmed(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)
        headers = self._session_headers(db_backed_client, installation)

        response = db_backed_client.post(
            f"/api/v1/widget/{installation.public_id}/appointment-requests",
            json={"requested_date": "2027-01-15", "timezone": "UTC", "requested_time_window": "morning"},
            headers=headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "pending"
        assert "pending confirmation" in body["message"].lower()
        # Reference must not be a raw sequential id.
        assert len(body["reference"]) >= 32

    def test_appointment_request_rejects_past_date(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)
        headers = self._session_headers(db_backed_client, installation)

        response = db_backed_client.post(
            f"/api/v1/widget/{installation.public_id}/appointment-requests",
            json={"requested_date": "2020-01-01", "timezone": "UTC"},
            headers=headers,
        )
        assert response.status_code == 422

    def test_appointment_request_with_valid_service_and_location_is_stored_and_visible_in_dashboard_records(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)
        location = BusinessLocation(tenant_id=tenant.id, name="Downtown", timezone="UTC")
        service = Service(tenant_id=tenant.id, name="Consultation")
        db_session.add_all([location, service])
        db_session.flush()
        headers = self._session_headers(db_backed_client, installation)

        response = db_backed_client.post(
            f"/api/v1/widget/{installation.public_id}/appointment-requests",
            json={
                "requested_date": "2027-01-15",
                "timezone": "UTC",
                "service_id": str(service.id),
                "location_id": str(location.id),
            },
            headers=headers,
        )
        assert response.status_code == 201

        # Verify the selection survives a save + a fresh authenticated
        # dashboard read (not just the in-memory response we just got).
        dashboard_response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/widget-records/appointment-requests", headers=_auth_headers(owner)
        )
        assert dashboard_response.status_code == 200
        [record] = dashboard_response.json()
        assert record["service_id"] == str(service.id)
        assert record["location_id"] == str(location.id)

    def test_appointment_request_with_inactive_service_is_rejected(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)
        service = Service(tenant_id=tenant.id, name="Retired", is_active=False)
        db_session.add(service)
        db_session.flush()
        headers = self._session_headers(db_backed_client, installation)

        response = db_backed_client.post(
            f"/api/v1/widget/{installation.public_id}/appointment-requests",
            json={"requested_date": "2027-01-15", "timezone": "UTC", "service_id": str(service.id)},
            headers=headers,
        )
        assert response.status_code == 422

    def test_appointment_request_with_unknown_service_id_is_rejected(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)
        headers = self._session_headers(db_backed_client, installation)

        response = db_backed_client.post(
            f"/api/v1/widget/{installation.public_id}/appointment-requests",
            json={"requested_date": "2027-01-15", "timezone": "UTC", "service_id": str(uuid.uuid4())},
            headers=headers,
        )
        assert response.status_code == 422

    def test_appointment_request_with_cross_tenant_service_id_is_rejected(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, _, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)
        other_tenant, _, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        other_service = Service(tenant_id=other_tenant.id, name="Someone Else's Service")
        db_session.add(other_service)
        db_session.flush()
        headers = self._session_headers(db_backed_client, installation)

        response = db_backed_client.post(
            f"/api/v1/widget/{installation.public_id}/appointment-requests",
            json={"requested_date": "2027-01-15", "timezone": "UTC", "service_id": str(other_service.id)},
            headers=headers,
        )
        assert response.status_code == 422

    def test_appointment_request_with_cross_tenant_location_id_is_rejected(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, _, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)
        other_tenant, _, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        other_location = BusinessLocation(tenant_id=other_tenant.id, name="Someone Else's Office", timezone="UTC")
        db_session.add(other_location)
        db_session.flush()
        headers = self._session_headers(db_backed_client, installation)

        response = db_backed_client.post(
            f"/api/v1/widget/{installation.public_id}/appointment-requests",
            json={"requested_date": "2027-01-15", "timezone": "UTC", "location_id": str(other_location.id)},
            headers=headers,
        )
        assert response.status_code == 422

    def test_handoff_request_does_not_promise_immediate_response(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)
        headers = self._session_headers(db_backed_client, installation)

        response = db_backed_client.post(
            f"/api/v1/widget/{installation.public_id}/handoff-requests",
            json={"reason": "I would like to speak with someone about pricing."},
            headers=headers,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "open"
        assert "does not connect you immediately" in body["message"].lower()

    def test_duplicate_handoff_clicks_do_not_create_duplicates(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)
        headers = self._session_headers(db_backed_client, installation)

        payload = {"reason": "Please call me back."}
        first = db_backed_client.post(
            f"/api/v1/widget/{installation.public_id}/handoff-requests", json=payload, headers=headers
        )
        second = db_backed_client.post(
            f"/api/v1/widget/{installation.public_id}/handoff-requests", json=payload, headers=headers
        )
        assert first.json()["reference"] == second.json()["reference"]

    def test_rate_limit_exceeded_returns_429_with_retry_after(self, db_backed_client: TestClient, db_session: Session):
        """Also locks in that HTTPException headers (Retry-After) survive the
        app's custom exception handler — caught live during Phase 5 E2E
        verification, where a real 429 response was missing this header
        because app/core/errors.py's handler rebuilt the JSONResponse from
        scratch without forwarding exc.headers."""
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        installation = _active_installation(db_session, tenant, receptionist)
        headers = self._session_headers(db_backed_client, installation)

        responses = [
            db_backed_client.post(
                f"/api/v1/widget/{installation.public_id}/handoff-requests",
                json={"reason": f"rate limit probe {i}"},
                headers=headers,
            )
            for i in range(6)
        ]

        assert [r.status_code for r in responses[:5]] == [201] * 5
        limited = responses[5]
        assert limited.status_code == 429
        assert "retry-after" in limited.headers
        assert int(limited.headers["retry-after"]) > 0


class TestWidgetInstallationManagement:
    def test_owner_can_create_and_activate_installation(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        headers = _auth_headers(owner)

        create_response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/widget-installations",
            json={"receptionist_id": str(receptionist.id), "allowed_domains": ["example.com"]},
            headers=headers,
        )
        assert create_response.status_code == 201
        installation_id = create_response.json()["id"]
        assert create_response.json()["status"] == "draft"

        activate_response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/widget-installations/{installation_id}/activate", headers=headers
        )
        assert activate_response.status_code == 200
        assert activate_response.json()["status"] == "active"

    def test_wildcard_domain_is_rejected(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        headers = _auth_headers(owner)

        response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/widget-installations",
            json={"receptionist_id": str(receptionist.id), "allowed_domains": ["*.example.com"]},
            headers=headers,
        )
        assert response.status_code == 422

    def test_embed_snippet_has_no_tenant_uuid(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = _active_receptionist(db_session, tenant)
        headers = _auth_headers(owner)

        create_response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/widget-installations",
            json={"receptionist_id": str(receptionist.id)},
            headers=headers,
        )
        installation_id = create_response.json()["id"]
        public_id = create_response.json()["public_id"]

        snippet_response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/widget-installations/{installation_id}/embed-snippet", headers=headers
        )
        assert snippet_response.status_code == 200
        snippet = snippet_response.json()["embed_snippet"]
        assert str(tenant.id) not in snippet
        assert public_id in snippet
