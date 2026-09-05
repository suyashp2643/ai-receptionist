import uuid
from datetime import UTC, date, datetime

from app.config import get_settings
from app.core.csv_export import build_csv
from app.core.security import create_access_token
from app.models.appointment_request import AppointmentRequest
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.enquiry import Enquiry
from app.models.enums import (
    AppointmentRequestStatus,
    ConversationChannel,
    ConversationMode,
    EnquiryStatus,
    HandoffStatus,
    TenantMemberRole,
)
from app.models.human_handoff import HumanHandoff
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import add_member, make_receptionist, make_tenant_with_owner, make_user

settings = get_settings()


def _auth_headers(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


class TestCsvInjectionProtection:
    def test_formula_prefixed_values_are_escaped(self):
        csv_text = build_csv(
            header=["name"], rows=[["=cmd|'/c calc'!A1"], ["+1+1"], ["-1"], ["@SUM(A1:A2)"], ["Normal"]]
        )
        lines = csv_text.lstrip("﻿").splitlines()
        assert lines[1] == "'=cmd|'/c calc'!A1"
        assert lines[2] == "'+1+1"
        assert lines[3] == "'-1"
        assert lines[4] == "'@SUM(A1:A2)"
        assert lines[5] == "Normal"

    def test_none_and_bool_cells_render_safely(self):
        csv_text = build_csv(header=["a", "b"], rows=[[None, True]])
        assert "\r\n" in csv_text
        assert ",True" in csv_text

    def test_row_count_limit_is_enforced(self):
        from app.core.csv_export import ExportTooLargeError

        try:
            build_csv(header=["a"], rows=([str(i)] for i in range(5)), max_rows=3)
            raise AssertionError("expected ExportTooLargeError")
        except ExportTooLargeError:
            pass


class TestExportEndpoint:
    def test_owner_can_export_contacts(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        db_session.add(Contact(tenant_id=tenant.id, name="=EVIL(1)", normalized_email="pat@example.com"))
        db_session.flush()

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/exports/contacts",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
            headers=_auth_headers(owner),
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        data_lines = [line for line in response.text.splitlines() if "EVIL" in line]
        assert len(data_lines) == 1
        assert ",'=EVIL(1)," in data_lines[0]
        assert ",=EVIL(1)," not in data_lines[0]

    def test_member_cannot_export(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        member_user = make_user(db_session)
        add_member(db_session, tenant=tenant, user=member_user, role=TenantMemberRole.MEMBER)

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/exports/contacts",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
            headers=_auth_headers(member_user),
        )
        assert response.status_code == 403

    def test_excessive_range_is_rejected(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/exports/contacts",
            params={"date_from": "2020-01-01", "date_to": "2025-01-01"},
            headers=_auth_headers(owner),
        )
        assert response.status_code == 422

    def test_unknown_entity_is_404(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/exports/not-a-real-entity",
            params={"date_from": "2020-01-01", "date_to": "2021-01-01"},
            headers=_auth_headers(owner),
        )
        assert response.status_code in (404, 422)

    def test_export_never_includes_another_tenants_rows(self, db_backed_client: TestClient, db_session: Session):
        """Phase 9 audit finding: this admin-only, PII-bearing surface had
        no test proving Tenant A cannot download Tenant B's rows via its
        own export endpoint."""
        tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, _, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        db_session.add(Contact(tenant_id=tenant_a.id, name="Tenant A Contact", normalized_email="a@example.com"))
        db_session.add(Contact(tenant_id=tenant_b.id, name="Tenant B Contact", normalized_email="b@example.com"))
        db_session.flush()

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant_a.id}/exports/contacts",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
            headers=_auth_headers(owner_a),
        )
        assert response.status_code == 200
        assert "Tenant A Contact" in response.text
        assert "Tenant B Contact" not in response.text
        assert "b@example.com" not in response.text

    def test_export_records_an_activity_event(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/exports/contacts",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
            headers=_auth_headers(owner),
        )
        activity = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/activity", params={"entity_type": "export"}, headers=_auth_headers(owner)
        )
        events = activity.json()["items"]
        assert any(e["action_type"] == "export.downloaded" for e in events)


class TestExportFilters:
    def _make_conversation(self, db, tenant, receptionist, mode=ConversationMode.WIDGET):
        conv = Conversation(
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            mode=mode,
            channel=ConversationChannel.WIDGET
            if mode == ConversationMode.WIDGET
            else ConversationChannel.DASHBOARD_TEST,
            provider="mock",
            started_at=datetime.now(UTC),
        )
        db.add(conv)
        db.flush()
        return conv

    def test_enquiry_export_status_filter_narrows_rows(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv_a = self._make_conversation(db_session, tenant, receptionist)
        conv_b = self._make_conversation(db_session, tenant, receptionist)
        db_session.add(
            Enquiry(
                tenant_id=tenant.id,
                receptionist_id=receptionist.id,
                conversation_id=conv_a.id,
                status=EnquiryStatus.NEW,
            )
        )
        db_session.add(
            Enquiry(
                tenant_id=tenant.id,
                receptionist_id=receptionist.id,
                conversation_id=conv_b.id,
                status=EnquiryStatus.QUALIFIED,
            )
        )
        db_session.flush()

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/exports/enquiries",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31", "status": "qualified"},
            headers=_auth_headers(owner),
        )
        assert response.status_code == 200
        data_lines = [line for line in response.text.splitlines()[1:] if line.strip()]
        assert len(data_lines) == 1
        assert "qualified" in data_lines[0]

    def test_conversation_export_source_filter_narrows_rows(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        self._make_conversation(db_session, tenant, receptionist, mode=ConversationMode.WIDGET)
        self._make_conversation(db_session, tenant, receptionist, mode=ConversationMode.TEST)
        db_session.flush()

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/exports/conversations",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31", "source": "test"},
            headers=_auth_headers(owner),
        )
        assert response.status_code == 200
        data_lines = [line for line in response.text.splitlines()[1:] if line.strip()]
        assert len(data_lines) == 1
        assert ",test," in data_lines[0]

    def test_invalid_status_filter_value_is_rejected(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/exports/enquiries",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31", "status": "not-a-real-status"},
            headers=_auth_headers(owner),
        )
        assert response.status_code == 422

    def test_all_five_entities_export_successfully(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = self._make_conversation(db_session, tenant, receptionist)
        db_session.add(Contact(tenant_id=tenant.id, conversation_id=conv.id, name="Pat"))
        db_session.add(
            Enquiry(
                tenant_id=tenant.id, receptionist_id=receptionist.id, conversation_id=conv.id, status=EnquiryStatus.NEW
            )
        )
        db_session.add(
            AppointmentRequest(
                tenant_id=tenant.id,
                receptionist_id=receptionist.id,
                conversation_id=conv.id,
                requested_date=date(2026, 6, 1),
                timezone="UTC",
                status=AppointmentRequestStatus.PENDING,
            )
        )
        db_session.add(
            HumanHandoff(
                tenant_id=tenant.id,
                receptionist_id=receptionist.id,
                conversation_id=conv.id,
                reason="test",
                status=HandoffStatus.OPEN,
            )
        )
        db_session.flush()

        for entity in ["conversations", "contacts", "enquiries", "appointments", "handoffs"]:
            response = db_backed_client.get(
                f"/api/v1/tenants/{tenant.id}/exports/{entity}",
                params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
                headers=_auth_headers(owner),
            )
            assert response.status_code == 200, f"{entity} export failed: {response.text}"
            lines = [line for line in response.text.splitlines()[1:] if line.strip()]
            assert len(lines) == 1, f"{entity} export expected exactly one data row, got {len(lines)}"
