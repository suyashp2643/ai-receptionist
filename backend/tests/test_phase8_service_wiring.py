"""Proves the four Phase 8-wired services actually produce outbox rows for
a subscribed connection — not just that outbox_producer_service works in
isolation (tests/test_phase8_outbox_producer.py already covers that), but
that contact_service/enquiry_service/appointment_request_service/
human_handoff_service call it correctly at the right points and only
those points (e.g. a repeat contact submission must NOT re-fire
contact.captured)."""

from datetime import date

from app.models.conversation import Conversation
from app.models.enums import (
    ConversationChannel,
    ConversationMode,
    ConversationStatus,
    HandoffStatus,
    IntegrationConnectionStatus,
    IntegrationConnectorType,
)
from app.models.integration import IntegrationConnection, IntegrationOutboxEvent
from app.services import appointment_request_service, contact_service, enquiry_service, human_handoff_service
from sqlalchemy import select

from tests.factories import make_tenant

ALL_PHASE8_EVENT_TYPES = [
    "contact.captured",
    "enquiry.created",
    "enquiry.qualified",
    "enquiry.status_changed",
    "appointment_request.created",
    "appointment_request.status_changed",
    "human_handoff.requested",
    "human_handoff.status_changed",
]


def _subscribed_connection(db, tenant) -> IntegrationConnection:
    connection = IntegrationConnection(
        tenant_id=tenant.id,
        connector_type=IntegrationConnectorType.MOCK,
        name="Wiring Test Connection",
        status=IntegrationConnectionStatus.CONFIGURED,
        config={"mode": "success"},
        enabled_event_types=ALL_PHASE8_EVENT_TYPES,
    )
    db.add(connection)
    db.flush()
    return connection


def _outbox_rows(db, connection_id):
    return db.scalars(select(IntegrationOutboxEvent).where(IntegrationOutboxEvent.connection_id == connection_id)).all()


def _make_receptionist_and_conversation(db, tenant):
    from app.models.industry_template import IndustryTemplate
    from app.models.receptionist import Receptionist

    template = db.scalars(select(IndustryTemplate)).first()
    if template is None:
        template = IndustryTemplate(key="generic", name="Generic", description="", default_workflow_config={})
        db.add(template)
        db.flush()

    receptionist = Receptionist(
        tenant_id=tenant.id,
        industry_template_id=template.id,
        name="Test Receptionist",
        welcome_message="Hi",
    )
    db.add(receptionist)
    db.flush()

    conversation = Conversation(
        tenant_id=tenant.id,
        receptionist_id=receptionist.id,
        mode=ConversationMode.WIDGET,
        channel=ConversationChannel.WIDGET,
        provider="mock",
        status=ConversationStatus.ACTIVE,
        locale="en",
        collected_data={"need": "a haircut"},
        missing_required_fields=[],
        qualification_complete=False,
    )
    db.add(conversation)
    db.flush()
    return receptionist, conversation


class TestContactServiceWiring:
    def test_new_contact_fires_contact_captured(self, db_session):
        tenant = make_tenant(db_session)
        connection = _subscribed_connection(db_session, tenant)
        contact_service.capture_contact(
            db_session,
            tenant_id=tenant.id,
            conversation_id=None,
            name="Jane Doe",
            email="jane@example.com",
            phone=None,
            preferred_contact_method=None,
            marketing_consent=False,
        )
        rows = _outbox_rows(db_session, connection.id)
        assert [r.event_type for r in rows] == ["contact.captured"]

    def test_a_repeat_submission_matching_an_existing_contact_does_not_refire(self, db_session):
        tenant = make_tenant(db_session)
        connection = _subscribed_connection(db_session, tenant)
        contact_service.capture_contact(
            db_session,
            tenant_id=tenant.id,
            conversation_id=None,
            name="Jane Doe",
            email="jane2@example.com",
            phone=None,
            preferred_contact_method=None,
            marketing_consent=False,
        )
        # Same email again — matches the existing contact, must not re-fire.
        contact_service.capture_contact(
            db_session,
            tenant_id=tenant.id,
            conversation_id=None,
            name=None,
            email="jane2@example.com",
            phone="+15551234567",
            preferred_contact_method=None,
            marketing_consent=False,
        )
        rows = _outbox_rows(db_session, connection.id)
        assert len(rows) == 1


class TestEnquiryServiceWiring:
    def test_first_upsert_fires_enquiry_created_only(self, db_session):
        tenant = make_tenant(db_session)
        connection = _subscribed_connection(db_session, tenant)
        _receptionist, conversation = _make_receptionist_and_conversation(db_session, tenant)

        enquiry_service.upsert_enquiry_from_conversation(db_session, tenant_id=tenant.id, conversation=conversation)

        rows = _outbox_rows(db_session, connection.id)
        assert [r.event_type for r in rows] == ["enquiry.created"]

    def test_qualification_completing_fires_enquiry_qualified_exactly_once(self, db_session):
        tenant = make_tenant(db_session)
        connection = _subscribed_connection(db_session, tenant)
        _receptionist, conversation = _make_receptionist_and_conversation(db_session, tenant)

        enquiry_service.upsert_enquiry_from_conversation(db_session, tenant_id=tenant.id, conversation=conversation)

        conversation.qualification_complete = True
        enquiry_service.upsert_enquiry_from_conversation(db_session, tenant_id=tenant.id, conversation=conversation)
        # A further turn after qualification must not re-fire.
        enquiry_service.upsert_enquiry_from_conversation(db_session, tenant_id=tenant.id, conversation=conversation)

        rows = _outbox_rows(db_session, connection.id)
        event_types = [r.event_type for r in rows]
        assert event_types.count("enquiry.created") == 1
        assert event_types.count("enquiry.qualified") == 1


class TestAppointmentRequestServiceWiring:
    def test_creation_fires_appointment_request_created(self, db_session):
        tenant = make_tenant(db_session)
        connection = _subscribed_connection(db_session, tenant)
        receptionist, conversation = _make_receptionist_and_conversation(db_session, tenant)

        appointment_request_service.create_appointment_request(
            db_session,
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            conversation_id=conversation.id,
            contact_id=None,
            location_id=None,
            service_id=None,
            requested_date=date.today(),
            requested_time=None,
            requested_time_window="morning",
            timezone="UTC",
            notes=None,
            idempotency_key=None,
        )
        rows = _outbox_rows(db_session, connection.id)
        assert [r.event_type for r in rows] == ["appointment_request.created"]

    def test_status_change_fires_appointment_request_status_changed(self, db_session):
        from app.models.enums import AppointmentRequestStatus, TenantMemberRole

        from tests.factories import add_member, make_user

        tenant = make_tenant(db_session)
        connection = _subscribed_connection(db_session, tenant)
        receptionist, conversation = _make_receptionist_and_conversation(db_session, tenant)
        owner = make_user(db_session)
        add_member(db_session, tenant=tenant, user=owner, role=TenantMemberRole.OWNER)

        request = appointment_request_service.create_appointment_request(
            db_session,
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            conversation_id=conversation.id,
            contact_id=None,
            location_id=None,
            service_id=None,
            requested_date=date.today(),
            requested_time=None,
            requested_time_window="morning",
            timezone="UTC",
            notes=None,
            idempotency_key=None,
        )
        appointment_request_service.update_status(
            db_session,
            tenant_id=tenant.id,
            actor_user_id=owner.id,
            appointment_request=request,
            new_status=AppointmentRequestStatus.CONFIRMED,
            expected_version=request.version,
        )
        rows = _outbox_rows(db_session, connection.id)
        event_types = [r.event_type for r in rows]
        assert event_types == ["appointment_request.created", "appointment_request.status_changed"]


class TestHumanHandoffServiceWiring:
    def test_creation_fires_human_handoff_requested(self, db_session):
        tenant = make_tenant(db_session)
        connection = _subscribed_connection(db_session, tenant)
        receptionist, conversation = _make_receptionist_and_conversation(db_session, tenant)

        human_handoff_service.create_handoff_request(
            db_session,
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            conversation_id=conversation.id,
            contact_id=None,
            reason="Please call me back",
            urgency=None,
            preferred_contact_method=None,
            idempotency_key=None,
        )
        rows = _outbox_rows(db_session, connection.id)
        assert [r.event_type for r in rows] == ["human_handoff.requested"]

    def test_claim_fires_human_handoff_status_changed(self, db_session):
        from app.models.enums import TenantMemberRole

        from tests.factories import add_member, make_user

        tenant = make_tenant(db_session)
        connection = _subscribed_connection(db_session, tenant)
        receptionist, conversation = _make_receptionist_and_conversation(db_session, tenant)
        owner = make_user(db_session)
        add_member(db_session, tenant=tenant, user=owner, role=TenantMemberRole.OWNER)

        handoff = human_handoff_service.create_handoff_request(
            db_session,
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            conversation_id=conversation.id,
            contact_id=None,
            reason="Please call me back",
            urgency=None,
            preferred_contact_method=None,
            idempotency_key=None,
        )
        human_handoff_service.claim(db_session, tenant_id=tenant.id, actor_user_id=owner.id, handoff_id=handoff.id)

        rows = _outbox_rows(db_session, connection.id)
        event_types = [r.event_type for r in rows]
        assert event_types == ["human_handoff.requested", "human_handoff.status_changed"]
        status_row = next(r for r in rows if r.event_type == "human_handoff.status_changed")
        assert status_row.payload["data"]["new_status"] == HandoffStatus.CLAIMED.value
