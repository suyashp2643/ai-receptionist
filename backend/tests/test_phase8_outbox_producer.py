"""Uses the rolled-back-at-the-end `db_session` fixture — safe because
`outbox_producer_service.produce_event` takes an explicit `Session` and
never opens its own (unlike the worker, which always uses the real
`session_scope()` — see tests/integration/test_phase8_outbox_worker.py for
why that module needs the real-commit multiconn pattern instead)."""

import uuid

from app.integrations.envelope import ContactCapturedPayload, ContactSummaryPayload, EventType
from app.models.enums import IntegrationConnectionStatus, IntegrationConnectorType
from app.models.integration import IntegrationConnection, IntegrationOutboxEvent
from app.services import outbox_producer_service
from sqlalchemy import select

from tests.factories import make_tenant


def _make_connection(
    db,
    *,
    tenant,
    connector_type=IntegrationConnectorType.MOCK,
    status=IntegrationConnectionStatus.CONFIGURED,
    enabled_event_types=None,
    name="Test Connection",
) -> IntegrationConnection:
    connection = IntegrationConnection(
        tenant_id=tenant.id,
        connector_type=connector_type,
        name=name,
        status=status,
        config={"mode": "success"},
        enabled_event_types=enabled_event_types or [],
    )
    db.add(connection)
    db.flush()
    return connection


def _contact_payload() -> ContactCapturedPayload:
    return ContactCapturedPayload(
        contact=ContactSummaryPayload(contact_id=uuid.uuid4(), marketing_consent=False, source="widget")
    )


class TestSubscriptionFiltering:
    def test_produces_no_rows_when_no_connection_is_subscribed(self, db_session):
        tenant = make_tenant(db_session)
        _make_connection(db_session, tenant=tenant, enabled_event_types=["enquiry.qualified"])
        produced = outbox_producer_service.produce_event(
            db_session,
            tenant_id=tenant.id,
            event_type=EventType.CONTACT_CAPTURED,
            payload=_contact_payload(),
            dedup_key="dk-1",
        )
        assert produced == 0
        assert db_session.scalars(select(IntegrationOutboxEvent)).all() == []

    def test_produces_a_row_for_a_subscribed_connection(self, db_session):
        tenant = make_tenant(db_session)
        connection = _make_connection(db_session, tenant=tenant, enabled_event_types=["contact.captured"])
        produced = outbox_producer_service.produce_event(
            db_session,
            tenant_id=tenant.id,
            event_type=EventType.CONTACT_CAPTURED,
            payload=_contact_payload(),
            dedup_key="dk-2",
        )
        assert produced == 1
        rows = db_session.scalars(select(IntegrationOutboxEvent)).all()
        assert len(rows) == 1
        assert rows[0].connection_id == connection.id
        assert rows[0].event_type == "contact.captured"

    def test_produces_one_row_per_subscribed_connection(self, db_session):
        tenant = make_tenant(db_session)
        _make_connection(db_session, tenant=tenant, enabled_event_types=["contact.captured"], name="A")
        _make_connection(db_session, tenant=tenant, enabled_event_types=["contact.captured"], name="B")
        produced = outbox_producer_service.produce_event(
            db_session,
            tenant_id=tenant.id,
            event_type=EventType.CONTACT_CAPTURED,
            payload=_contact_payload(),
            dedup_key="dk-3",
        )
        assert produced == 2

    def test_skips_a_paused_connection(self, db_session):
        tenant = make_tenant(db_session)
        _make_connection(
            db_session,
            tenant=tenant,
            enabled_event_types=["contact.captured"],
            status=IntegrationConnectionStatus.PAUSED,
        )
        produced = outbox_producer_service.produce_event(
            db_session,
            tenant_id=tenant.id,
            event_type=EventType.CONTACT_CAPTURED,
            payload=_contact_payload(),
            dedup_key="dk-4",
        )
        assert produced == 0

    def test_skips_a_disabled_connection(self, db_session):
        tenant = make_tenant(db_session)
        _make_connection(
            db_session,
            tenant=tenant,
            enabled_event_types=["contact.captured"],
            status=IntegrationConnectionStatus.DISABLED,
        )
        produced = outbox_producer_service.produce_event(
            db_session,
            tenant_id=tenant.id,
            event_type=EventType.CONTACT_CAPTURED,
            payload=_contact_payload(),
            dedup_key="dk-5",
        )
        assert produced == 0

    def test_never_produces_for_another_tenants_connection(self, db_session):
        tenant_a = make_tenant(db_session, name="Tenant A")
        tenant_b = make_tenant(db_session, name="Tenant B")
        _make_connection(db_session, tenant=tenant_b, enabled_event_types=["contact.captured"])
        produced = outbox_producer_service.produce_event(
            db_session,
            tenant_id=tenant_a.id,
            event_type=EventType.CONTACT_CAPTURED,
            payload=_contact_payload(),
            dedup_key="dk-6",
        )
        assert produced == 0


class TestIdempotentProduction:
    def test_the_same_dedup_key_produces_only_one_row(self, db_session):
        tenant = make_tenant(db_session)
        _make_connection(db_session, tenant=tenant, enabled_event_types=["contact.captured"])
        payload = _contact_payload()
        first = outbox_producer_service.produce_event(
            db_session,
            tenant_id=tenant.id,
            event_type=EventType.CONTACT_CAPTURED,
            payload=payload,
            dedup_key="same-key",
        )
        second = outbox_producer_service.produce_event(
            db_session,
            tenant_id=tenant.id,
            event_type=EventType.CONTACT_CAPTURED,
            payload=payload,
            dedup_key="same-key",
        )
        assert first == 1
        assert second == 0
        rows = db_session.scalars(select(IntegrationOutboxEvent)).all()
        assert len(rows) == 1

    def test_different_dedup_keys_produce_separate_rows(self, db_session):
        tenant = make_tenant(db_session)
        _make_connection(db_session, tenant=tenant, enabled_event_types=["contact.captured"])
        payload = _contact_payload()
        outbox_producer_service.produce_event(
            db_session, tenant_id=tenant.id, event_type=EventType.CONTACT_CAPTURED, payload=payload, dedup_key="key-a"
        )
        outbox_producer_service.produce_event(
            db_session, tenant_id=tenant.id, event_type=EventType.CONTACT_CAPTURED, payload=payload, dedup_key="key-b"
        )
        rows = db_session.scalars(select(IntegrationOutboxEvent)).all()
        assert len(rows) == 2


class TestSalesEmployeeEventScopeEnforcement:
    def test_safety_escalation_is_never_produced_for_a_sales_employee_connection(self, db_session):
        tenant = make_tenant(db_session)
        _make_connection(
            db_session,
            tenant=tenant,
            connector_type=IntegrationConnectorType.SALES_EMPLOYEE,
            status=IntegrationConnectionStatus.CONFIGURED,
            enabled_event_types=["safety.escalation_detected"],
        )
        from app.integrations.envelope import SafetyEscalationDetectedPayload

        produced = outbox_producer_service.produce_event(
            db_session,
            tenant_id=tenant.id,
            event_type=EventType.SAFETY_ESCALATION_DETECTED,
            payload=SafetyEscalationDetectedPayload(
                conversation_id=uuid.uuid4(), receptionist_id=uuid.uuid4(), category="clinic_urgent", channel="widget"
            ),
            dedup_key="dk-safety",
        )
        assert produced == 0


class TestTestEventProduction:
    def test_produce_test_event_always_creates_a_row(self, db_session):
        tenant = make_tenant(db_session)
        connection = _make_connection(db_session, tenant=tenant, status=IntegrationConnectionStatus.DISABLED)
        row = outbox_producer_service.produce_test_event(db_session, connection=connection, triggered_by="dashboard")
        assert row.event_type == "connection.test_event"
        assert row.connection_id == connection.id

    def test_produce_test_event_is_not_deduplicated(self, db_session):
        tenant = make_tenant(db_session)
        connection = _make_connection(db_session, tenant=tenant)
        outbox_producer_service.produce_test_event(db_session, connection=connection, triggered_by="a")
        outbox_producer_service.produce_test_event(db_session, connection=connection, triggered_by="b")
        rows = db_session.scalars(
            select(IntegrationOutboxEvent).where(IntegrationOutboxEvent.connection_id == connection.id)
        ).all()
        assert len(rows) == 2
