import uuid
from datetime import date

from app.config import get_settings
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


def _make_conversation(db, *, tenant_id, receptionist_id) -> Conversation:
    conv = Conversation(
        tenant_id=tenant_id,
        receptionist_id=receptionist_id,
        mode=ConversationMode.WIDGET,
        channel=ConversationChannel.WIDGET,
        provider="mock",
    )
    db.add(conv)
    db.flush()
    return conv


class TestContacts:
    def test_list_and_detail(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        contact = Contact(tenant_id=tenant.id, conversation_id=conv.id, name="Pat", normalized_email="pat@example.com")
        db_session.add(contact)
        db_session.flush()

        list_response = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/contacts", headers=_auth_headers(owner))
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1

        detail_response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/contacts/{contact.id}", headers=_auth_headers(owner)
        )
        assert detail_response.status_code == 200
        assert detail_response.json()["normalized_email"] == "pat@example.com"

    def test_cross_tenant_contact_is_404(self, db_backed_client: TestClient, db_session: Session):
        tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="A")
        tenant_b, _, _ = make_tenant_with_owner(db_session, tenant_name="B")
        receptionist_b, _ = make_receptionist(db_session, tenant=tenant_b)
        conv_b = _make_conversation(db_session, tenant_id=tenant_b.id, receptionist_id=receptionist_b.id)
        contact_b = Contact(tenant_id=tenant_b.id, conversation_id=conv_b.id, name="Other")
        db_session.add(contact_b)
        db_session.flush()

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant_a.id}/contacts/{contact_b.id}", headers=_auth_headers(owner_a)
        )
        assert response.status_code == 404


class TestEnquiryStatusUpdate:
    def _make_enquiry(self, db, tenant, receptionist, conv, status=EnquiryStatus.NEW):
        enquiry = Enquiry(tenant_id=tenant.id, receptionist_id=receptionist.id, conversation_id=conv.id, status=status)
        db.add(enquiry)
        db.flush()
        return enquiry

    def test_valid_transition_succeeds_and_records_activity(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        enquiry = self._make_enquiry(db_session, tenant, receptionist, conv)

        response = db_backed_client.patch(
            f"/api/v1/tenants/{tenant.id}/enquiries/{enquiry.id}/status",
            json={"status": "qualified", "expected_version": 1},
            headers=_auth_headers(owner),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "qualified"
        assert body["version"] == 2

        activity_response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/activity", params={"entity_type": "enquiry"}, headers=_auth_headers(owner)
        )
        events = activity_response.json()["items"]
        assert any(e["action_type"] == "enquiry.status_changed" for e in events)

    def test_invalid_transition_is_rejected(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        enquiry = self._make_enquiry(db_session, tenant, receptionist, conv, status=EnquiryStatus.ARCHIVED)

        response = db_backed_client.patch(
            f"/api/v1/tenants/{tenant.id}/enquiries/{enquiry.id}/status",
            json={"status": "won", "expected_version": 1},
            headers=_auth_headers(owner),
        )
        assert response.status_code == 422

    def test_stale_version_is_rejected(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        enquiry = self._make_enquiry(db_session, tenant, receptionist, conv)

        response = db_backed_client.patch(
            f"/api/v1/tenants/{tenant.id}/enquiries/{enquiry.id}/status",
            json={"status": "qualified", "expected_version": 999},
            headers=_auth_headers(owner),
        )
        assert response.status_code == 409

    def test_member_can_update_enquiry_status(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        enquiry = self._make_enquiry(db_session, tenant, receptionist, conv)
        member_user = make_user(db_session)
        add_member(db_session, tenant=tenant, user=member_user, role=TenantMemberRole.MEMBER)

        response = db_backed_client.patch(
            f"/api/v1/tenants/{tenant.id}/enquiries/{enquiry.id}/status",
            json={"status": "qualified", "expected_version": 1},
            headers=_auth_headers(member_user),
        )
        assert response.status_code == 200

    def test_cross_tenant_enquiry_is_404_for_get_and_update(
        self, db_backed_client: TestClient, db_session: Session
    ):
        """Phase 9 audit finding: enquiries had no dedicated cross-tenant
        HTTP regression test, relying entirely on the shared
        TenantScopedRepository guarantee with no test of its own."""
        tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="A")
        tenant_b, _, _ = make_tenant_with_owner(db_session, tenant_name="B")
        receptionist_b, _ = make_receptionist(db_session, tenant=tenant_b)
        conv_b = _make_conversation(db_session, tenant_id=tenant_b.id, receptionist_id=receptionist_b.id)
        enquiry_b = self._make_enquiry(db_session, tenant_b, receptionist_b, conv_b)

        get_response = db_backed_client.get(
            f"/api/v1/tenants/{tenant_a.id}/enquiries/{enquiry_b.id}", headers=_auth_headers(owner_a)
        )
        assert get_response.status_code == 404

        patch_response = db_backed_client.patch(
            f"/api/v1/tenants/{tenant_a.id}/enquiries/{enquiry_b.id}/status",
            json={"status": "qualified", "expected_version": 1},
            headers=_auth_headers(owner_a),
        )
        assert patch_response.status_code == 404

        db_session.refresh(enquiry_b)
        assert enquiry_b.status == EnquiryStatus.NEW


class TestAppointmentStatusUpdate:
    def _make_appointment(self, db, tenant, receptionist, conv, status=AppointmentRequestStatus.PENDING):
        appt = AppointmentRequest(
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            conversation_id=conv.id,
            requested_date=date(2026, 3, 1),
            timezone="UTC",
            status=status,
        )
        db.add(appt)
        db.flush()
        return appt

    def test_owner_can_confirm(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        appt = self._make_appointment(db_session, tenant, receptionist, conv)

        response = db_backed_client.patch(
            f"/api/v1/tenants/{tenant.id}/appointments/{appt.id}/status",
            json={"status": "confirmed", "expected_version": 1},
            headers=_auth_headers(owner),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"

    def test_member_cannot_confirm(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        appt = self._make_appointment(db_session, tenant, receptionist, conv)
        member_user = make_user(db_session)
        add_member(db_session, tenant=tenant, user=member_user, role=TenantMemberRole.MEMBER)

        response = db_backed_client.patch(
            f"/api/v1/tenants/{tenant.id}/appointments/{appt.id}/status",
            json={"status": "confirmed", "expected_version": 1},
            headers=_auth_headers(member_user),
        )
        assert response.status_code == 403

    def test_declined_is_terminal(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        appt = self._make_appointment(db_session, tenant, receptionist, conv, status=AppointmentRequestStatus.DECLINED)

        response = db_backed_client.patch(
            f"/api/v1/tenants/{tenant.id}/appointments/{appt.id}/status",
            json={"status": "confirmed", "expected_version": 1},
            headers=_auth_headers(owner),
        )
        assert response.status_code == 422

    def test_cross_tenant_appointment_is_404_for_get_and_update(
        self, db_backed_client: TestClient, db_session: Session
    ):
        """Phase 9 audit finding: appointments had no dedicated cross-tenant
        HTTP regression test."""
        tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="A")
        tenant_b, _, _ = make_tenant_with_owner(db_session, tenant_name="B")
        receptionist_b, _ = make_receptionist(db_session, tenant=tenant_b)
        conv_b = _make_conversation(db_session, tenant_id=tenant_b.id, receptionist_id=receptionist_b.id)
        appt_b = self._make_appointment(db_session, tenant_b, receptionist_b, conv_b)

        get_response = db_backed_client.get(
            f"/api/v1/tenants/{tenant_a.id}/appointments/{appt_b.id}", headers=_auth_headers(owner_a)
        )
        assert get_response.status_code == 404

        patch_response = db_backed_client.patch(
            f"/api/v1/tenants/{tenant_a.id}/appointments/{appt_b.id}/status",
            json={"status": "confirmed", "expected_version": 1},
            headers=_auth_headers(owner_a),
        )
        assert patch_response.status_code == 404

        db_session.refresh(appt_b)
        assert appt_b.status == AppointmentRequestStatus.PENDING


class TestHandoffClaimAndStatus:
    def _make_handoff(self, db, tenant, receptionist, conv, status=HandoffStatus.OPEN):
        handoff = HumanHandoff(
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            conversation_id=conv.id,
            reason="Call me back",
            status=status,
        )
        db.add(handoff)
        db.flush()
        return handoff

    def test_member_can_claim_open_handoff(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        handoff = self._make_handoff(db_session, tenant, receptionist, conv)
        member_user = make_user(db_session)
        add_member(db_session, tenant=tenant, user=member_user, role=TenantMemberRole.MEMBER)

        response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/handoffs/{handoff.id}/claim", headers=_auth_headers(member_user)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "claimed"
        assert body["assigned_user_id"] == str(member_user.id)

    def test_claiming_an_already_claimed_handoff_conflicts(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        handoff = self._make_handoff(db_session, tenant, receptionist, conv, status=HandoffStatus.CLAIMED)

        response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/handoffs/{handoff.id}/claim", headers=_auth_headers(owner)
        )
        assert response.status_code == 409

    def test_claim_attempt_on_a_claimed_handoff_via_service_layer_raises(self, db_session: Session):
        """Fast, single-connection check of claim()'s error path — the
        genuine cross-connection race (two distinct tenant members racing
        the atomic UPDATE against real, separate database connections) is
        covered by tests/integration/test_handoff_claim_concurrency.py,
        which `pytest -m multiconn` selects."""
        from app.services import human_handoff_service
        from app.services.human_handoff_service import HandoffAlreadyClaimedError

        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        handoff = self._make_handoff(db_session, tenant, receptionist, conv)
        user_a = make_user(db_session)
        user_b = make_user(db_session)

        claimed = human_handoff_service.claim(
            db_session, tenant_id=tenant.id, actor_user_id=user_a.id, handoff_id=handoff.id
        )
        assert claimed.status == HandoffStatus.CLAIMED

        try:
            human_handoff_service.claim(db_session, tenant_id=tenant.id, actor_user_id=user_b.id, handoff_id=handoff.id)
            raise AssertionError("expected HandoffAlreadyClaimedError")
        except HandoffAlreadyClaimedError:
            pass

    def test_resolve_requires_claimed_first(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        handoff = self._make_handoff(db_session, tenant, receptionist, conv, status=HandoffStatus.OPEN)

        response = db_backed_client.patch(
            f"/api/v1/tenants/{tenant.id}/handoffs/{handoff.id}/status",
            json={"status": "resolved", "expected_version": 1},
            headers=_auth_headers(owner),
        )
        assert response.status_code == 422

    def test_member_cannot_cancel_handoff(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        handoff = self._make_handoff(db_session, tenant, receptionist, conv, status=HandoffStatus.OPEN)
        member_user = make_user(db_session)
        add_member(db_session, tenant=tenant, user=member_user, role=TenantMemberRole.MEMBER)

        response = db_backed_client.patch(
            f"/api/v1/tenants/{tenant.id}/handoffs/{handoff.id}/status",
            json={"status": "cancelled", "expected_version": 1},
            headers=_auth_headers(member_user),
        )
        assert response.status_code == 403

    def test_clinic_emergency_conversation_flag_visible_on_handoff(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        conv.had_clinic_emergency = True
        handoff = self._make_handoff(db_session, tenant, receptionist, conv)

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/handoffs/{handoff.id}", headers=_auth_headers(owner)
        )
        assert response.status_code == 200
        assert response.json()["is_clinic_emergency"] is True

    def test_cross_tenant_handoff_is_404_for_get_claim_and_update(
        self, db_backed_client: TestClient, db_session: Session
    ):
        """Phase 9 audit finding: handoffs had no dedicated cross-tenant
        HTTP regression test — only claim-conflict tests existed."""
        tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="A")
        tenant_b, _, _ = make_tenant_with_owner(db_session, tenant_name="B")
        receptionist_b, _ = make_receptionist(db_session, tenant=tenant_b)
        conv_b = _make_conversation(db_session, tenant_id=tenant_b.id, receptionist_id=receptionist_b.id)
        handoff_b = self._make_handoff(db_session, tenant_b, receptionist_b, conv_b)

        get_response = db_backed_client.get(
            f"/api/v1/tenants/{tenant_a.id}/handoffs/{handoff_b.id}", headers=_auth_headers(owner_a)
        )
        assert get_response.status_code == 404

        claim_response = db_backed_client.post(
            f"/api/v1/tenants/{tenant_a.id}/handoffs/{handoff_b.id}/claim", headers=_auth_headers(owner_a)
        )
        assert claim_response.status_code == 404

        patch_response = db_backed_client.patch(
            f"/api/v1/tenants/{tenant_a.id}/handoffs/{handoff_b.id}/status",
            json={"status": "cancelled", "expected_version": 1},
            headers=_auth_headers(owner_a),
        )
        assert patch_response.status_code == 404

        db_session.refresh(handoff_b)
        assert handoff_b.status == HandoffStatus.OPEN
        assert handoff_b.assigned_user_id is None
