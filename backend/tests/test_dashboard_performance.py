"""Query-count regression tests for the primary dashboard endpoints, with a
meaningfully seeded volume (dozens of conversations/records) — the
requirement is that the number of SQL statements an endpoint issues stays
BOUNDED regardless of how many rows exist, which is exactly what an N+1
regression would violate (query count would grow with the seeded volume
instead of staying flat)."""

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime

from app.config import get_settings
from app.core.security import create_access_token
from app.models.appointment_request import AppointmentRequest
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.enquiry import Enquiry
from app.models.enums import (
    AppointmentRequestStatus,
    ConversationChannel,
    ConversationMessageRole,
    ConversationMode,
    HandoffStatus,
)
from app.models.human_handoff import HumanHandoff
from app.models.widget_installation import WidgetInstallation
from app.models.widget_visitor_session import WidgetVisitorSession
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from tests.factories import make_receptionist, make_tenant_with_owner

settings = get_settings()

SEED_CONVERSATION_COUNT = 40


def _auth_headers(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


@contextmanager
def count_queries(session: Session):
    counter = {"count": 0}
    connection = session.connection()

    def _on_execute(*_args, **_kwargs):
        counter["count"] += 1

    event.listen(connection, "before_cursor_execute", _on_execute)
    try:
        yield counter
    finally:
        event.remove(connection, "before_cursor_execute", _on_execute)


def _seed_dashboard_volume(db: Session, *, tenant, receptionist, count: int) -> None:
    installation = WidgetInstallation(tenant_id=tenant.id, receptionist_id=receptionist.id)
    db.add(installation)
    db.flush()
    for i in range(count):
        conv = Conversation(
            tenant_id=tenant.id,
            receptionist_id=receptionist.id,
            mode=ConversationMode.WIDGET,
            channel=ConversationChannel.WIDGET,
            provider="mock",
            started_at=datetime.now(UTC),
        )
        db.add(conv)
        db.flush()
        db.add(
            WidgetVisitorSession(
                tenant_id=tenant.id,
                widget_installation_id=installation.id,
                conversation_id=conv.id,
                token_hash=uuid.uuid4().hex,
                expires_at=datetime.now(UTC),
                is_platform_preview=False,
            )
        )
        for seq in range(3):
            db.add(
                ConversationMessage(
                    tenant_id=tenant.id,
                    conversation_id=conv.id,
                    role=ConversationMessageRole.USER if seq % 2 == 0 else ConversationMessageRole.ASSISTANT,
                    content=f"message {seq}",
                    sequence_number=seq,
                )
            )
        contact = Contact(tenant_id=tenant.id, conversation_id=conv.id, name=f"Contact {i}")
        db.add(contact)
        db.flush()
        db.add(
            Enquiry(
                tenant_id=tenant.id,
                receptionist_id=receptionist.id,
                conversation_id=conv.id,
                contact_id=contact.id,
                qualification_complete=(i % 2 == 0),
            )
        )
        db.add(
            AppointmentRequest(
                tenant_id=tenant.id,
                receptionist_id=receptionist.id,
                conversation_id=conv.id,
                contact_id=contact.id,
                requested_date=datetime.now(UTC).date(),
                timezone="UTC",
                status=AppointmentRequestStatus.PENDING,
            )
        )
        db.add(
            HumanHandoff(
                tenant_id=tenant.id,
                receptionist_id=receptionist.id,
                conversation_id=conv.id,
                contact_id=contact.id,
                reason="test",
                status=HandoffStatus.OPEN,
            )
        )
    db.flush()


class TestNoQueryCountRegressions:
    def test_analytics_overview_query_count_is_bounded(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        _seed_dashboard_volume(db_session, tenant=tenant, receptionist=receptionist, count=SEED_CONVERSATION_COUNT)
        db_session.commit()

        with count_queries(db_session) as counter:
            response = db_backed_client.get(
                f"/api/v1/tenants/{tenant.id}/analytics/overview", headers=_auth_headers(owner)
            )
        assert response.status_code == 200
        assert response.json()["total_conversations"] == SEED_CONVERSATION_COUNT
        # 8 explicit aggregate queries (conversations, sessions, contacts,
        # enquiries, appointments, handoffs, fallback messages,
        # response-time/length) plus a small constant for auth/tenant
        # lookups — must never scale with SEED_CONVERSATION_COUNT.
        assert (
            counter["count"] < 20
        ), f"analytics overview issued {counter['count']} queries for {SEED_CONVERSATION_COUNT} conversations"

    def test_conversation_list_query_count_is_bounded(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        _seed_dashboard_volume(db_session, tenant=tenant, receptionist=receptionist, count=SEED_CONVERSATION_COUNT)
        db_session.commit()

        with count_queries(db_session) as counter:
            response = db_backed_client.get(
                f"/api/v1/tenants/{tenant.id}/conversations",
                params={"limit": 25},
                headers=_auth_headers(owner),
            )
        assert response.status_code == 200
        assert response.json()["total"] == SEED_CONVERSATION_COUNT
        # One COUNT query + one paginated SELECT + a small constant for
        # auth/tenant lookups — never one query per returned row.
        assert counter["count"] < 10, f"conversation list issued {counter['count']} queries"

    def test_enquiry_list_query_count_is_bounded(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        _seed_dashboard_volume(db_session, tenant=tenant, receptionist=receptionist, count=SEED_CONVERSATION_COUNT)
        db_session.commit()

        with count_queries(db_session) as counter:
            response = db_backed_client.get(
                f"/api/v1/tenants/{tenant.id}/enquiries", params={"limit": 25}, headers=_auth_headers(owner)
            )
        assert response.status_code == 200
        assert response.json()["total"] == SEED_CONVERSATION_COUNT
        assert counter["count"] < 10, f"enquiry list issued {counter['count']} queries"
