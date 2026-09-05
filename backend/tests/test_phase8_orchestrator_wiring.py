"""Proves the orchestrator's two Phase 8 production points actually fire:
safety.escalation_detected (app/ai/orchestrator.py's phase-2 short
transaction) and conversation.completed (complete_conversation). Reuses
tests/test_conversations_api.py's own clinic-emergency setup so this is
exercised through the exact same safety-critical code path the existing
concurrency/lock-leak suite already covers — this file only adds outbox
assertions on top, it does not re-test safety detection itself."""

import uuid

from app.config import get_settings
from app.core.security import create_access_token
from app.models.enums import IntegrationConnectionStatus, IntegrationConnectorType
from app.models.integration import IntegrationConnection, IntegrationOutboxEvent
from app.seed_data.seed_runner import seed_industry_templates
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.factories import make_receptionist, make_tenant_with_owner
from tests.test_conversations_api import _send_message

settings = get_settings()


def _auth_headers(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


def _subscribed_connection(db: Session, tenant, event_types: list[str]) -> IntegrationConnection:
    connection = IntegrationConnection(
        tenant_id=tenant.id,
        connector_type=IntegrationConnectorType.MOCK,
        name="Orchestrator Wiring Test",
        status=IntegrationConnectionStatus.CONFIGURED,
        config={"mode": "success"},
        enabled_event_types=event_types,
    )
    db.add(connection)
    db.flush()
    return connection


def _outbox_event_types(db: Session, connection_id) -> list[str]:
    rows = db.scalars(select(IntegrationOutboxEvent).where(IntegrationOutboxEvent.connection_id == connection_id)).all()
    return [r.event_type for r in rows]


class TestSafetyEscalationWiring:
    def test_clinic_emergency_message_produces_safety_escalation_event(
        self, db_backed_client: TestClient, db_session: Session
    ):
        seed_industry_templates(db_session)
        tenant, owner, _ = make_tenant_with_owner(db_session)
        headers = _auth_headers(owner)
        db_backed_client.patch(
            f"/api/v1/tenants/{tenant.id}/business-profile", json={"business_name": "Test Clinic"}, headers=headers
        )
        db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/select-industry", json={"template_key": "clinic"}, headers=headers
        )
        receptionists = db_backed_client.get(f"/api/v1/tenants/{tenant.id}/receptionists", headers=headers)
        receptionist_id = receptionists.json()[0]["id"]
        db_backed_client.patch(
            f"/api/v1/tenants/{tenant.id}/receptionists/{receptionist_id}", json={"status": "active"}, headers=headers
        )
        connection = _subscribed_connection(db_session, tenant, ["safety.escalation_detected"])

        start = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/receptionists/{receptionist_id}/test-conversations",
            json={},
            headers=headers,
        )
        conversation_id = start.json()["id"]
        _, events = _send_message(
            db_backed_client, tenant.id, conversation_id, headers, "I'm having chest pain and can't breathe"
        )
        completed = next(e for e in events if e["event"] == "response.completed")
        assert "clinic_urgent" in completed["data"]["safety_labels"]

        event_types = _outbox_event_types(db_session, connection.id)
        assert event_types == ["safety.escalation_detected"]
        row = db_session.scalars(
            select(IntegrationOutboxEvent).where(IntegrationOutboxEvent.connection_id == connection.id)
        ).first()
        assert row.payload["data"]["category"] == "clinic_urgent"
        # Never the triggering message text — see envelope.py's PII policy.
        assert "chest pain" not in str(row.payload)

    def test_ordinary_message_does_not_produce_a_safety_event(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        from app.models.enums import ReceptionistStatus

        receptionist.status = ReceptionistStatus.ACTIVE
        db_session.flush()
        headers = _auth_headers(owner)
        connection = _subscribed_connection(db_session, tenant, ["safety.escalation_detected"])

        start = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/receptionists/{receptionist.id}/test-conversations",
            json={},
            headers=headers,
        )
        conversation_id = start.json()["id"]
        _send_message(db_backed_client, tenant.id, conversation_id, headers, "What are your hours?")

        assert _outbox_event_types(db_session, connection.id) == []


class TestConversationCompletedWiring:
    def test_completing_a_conversation_produces_conversation_completed(
        self, db_backed_client: TestClient, db_session: Session
    ):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        from app.models.enums import ReceptionistStatus

        receptionist.status = ReceptionistStatus.ACTIVE
        db_session.flush()
        headers = _auth_headers(owner)
        connection = _subscribed_connection(db_session, tenant, ["conversation.completed"])

        start = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/receptionists/{receptionist.id}/test-conversations",
            json={},
            headers=headers,
        )
        conversation_id = start.json()["id"]

        complete = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/test-conversations/{conversation_id}/complete", headers=headers
        )
        assert complete.status_code == 200

        event_types = _outbox_event_types(db_session, connection.id)
        assert event_types == ["conversation.completed"]
