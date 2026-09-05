"""Tests for the explicit, bounded stale-conversation sweep — the
producer for `conversation.abandoned` (see
app/services/conversation_sweep_service.py's own docstring for why this
is deliberately NOT a scheduler)."""

from datetime import UTC, datetime, timedelta

from app.models.conversation import Conversation
from app.models.enums import (
    ConversationChannel,
    ConversationMode,
    ConversationStatus,
    IntegrationConnectionStatus,
    IntegrationConnectorType,
)
from app.models.integration import IntegrationConnection, IntegrationOutboxEvent
from app.services.conversation_sweep_service import sweep_stale_conversations
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.factories import make_receptionist, make_tenant


def _make_conversation(
    db: Session,
    *,
    tenant,
    receptionist,
    last_message_minutes_ago: int | None,
    started_minutes_ago: int = 120,
    status=ConversationStatus.ACTIVE,
) -> Conversation:
    now = datetime.now(UTC)
    conversation = Conversation(
        tenant_id=tenant.id,
        receptionist_id=receptionist.id,
        mode=ConversationMode.WIDGET,
        channel=ConversationChannel.WIDGET,
        provider="mock",
        status=status,
        locale="en",
        collected_data={},
        missing_required_fields=[],
        qualification_complete=False,
        started_at=now - timedelta(minutes=started_minutes_ago),
        last_message_at=(now - timedelta(minutes=last_message_minutes_ago))
        if last_message_minutes_ago is not None
        else None,
    )
    db.add(conversation)
    db.flush()
    return conversation


def _subscribed_connection(db: Session, tenant) -> IntegrationConnection:
    connection = IntegrationConnection(
        tenant_id=tenant.id,
        connector_type=IntegrationConnectorType.MOCK,
        name="Sweep Test Connection",
        status=IntegrationConnectionStatus.CONFIGURED,
        config={"mode": "success"},
        enabled_event_types=["conversation.abandoned"],
    )
    db.add(connection)
    db.flush()
    return connection


class TestSweepStaleConversations:
    def test_a_stale_conversation_is_marked_abandoned(self, db_session: Session):
        tenant = make_tenant(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conversation = _make_conversation(
            db_session, tenant=tenant, receptionist=receptionist, last_message_minutes_ago=120
        )

        result = sweep_stale_conversations(db_session, stale_after_minutes=60, batch_limit=100)

        assert result.scanned == 1
        assert result.abandoned == 1
        db_session.refresh(conversation)
        assert conversation.status == ConversationStatus.ABANDONED

    def test_a_recent_conversation_is_not_touched(self, db_session: Session):
        tenant = make_tenant(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conversation = _make_conversation(
            db_session, tenant=tenant, receptionist=receptionist, last_message_minutes_ago=5
        )

        result = sweep_stale_conversations(db_session, stale_after_minutes=60, batch_limit=100)

        assert result.scanned == 0
        db_session.refresh(conversation)
        assert conversation.status == ConversationStatus.ACTIVE

    def test_falls_back_to_started_at_when_no_message_was_ever_sent(self, db_session: Session):
        tenant = make_tenant(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conversation = _make_conversation(
            db_session, tenant=tenant, receptionist=receptionist, last_message_minutes_ago=None, started_minutes_ago=120
        )

        result = sweep_stale_conversations(db_session, stale_after_minutes=60, batch_limit=100)

        assert result.abandoned == 1
        db_session.refresh(conversation)
        assert conversation.status == ConversationStatus.ABANDONED

    def test_completed_and_already_abandoned_conversations_are_never_touched(self, db_session: Session):
        tenant = make_tenant(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        _make_conversation(
            db_session,
            tenant=tenant,
            receptionist=receptionist,
            last_message_minutes_ago=120,
            status=ConversationStatus.COMPLETED,
        )
        _make_conversation(
            db_session,
            tenant=tenant,
            receptionist=receptionist,
            last_message_minutes_ago=120,
            status=ConversationStatus.ABANDONED,
        )

        result = sweep_stale_conversations(db_session, stale_after_minutes=60, batch_limit=100)
        assert result.scanned == 0

    def test_produces_a_conversation_abandoned_outbox_event(self, db_session: Session):
        tenant = make_tenant(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        connection = _subscribed_connection(db_session, tenant)
        _make_conversation(db_session, tenant=tenant, receptionist=receptionist, last_message_minutes_ago=120)

        sweep_stale_conversations(db_session, stale_after_minutes=60, batch_limit=100)

        rows = db_session.scalars(
            select(IntegrationOutboxEvent).where(IntegrationOutboxEvent.connection_id == connection.id)
        ).all()
        assert [r.event_type for r in rows] == ["conversation.abandoned"]

    def test_batch_limit_bounds_a_single_call(self, db_session: Session):
        tenant = make_tenant(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        for _ in range(5):
            _make_conversation(db_session, tenant=tenant, receptionist=receptionist, last_message_minutes_ago=120)

        result = sweep_stale_conversations(db_session, stale_after_minutes=60, batch_limit=2)
        assert result.scanned == 2
        assert result.abandoned == 2

    def test_tenant_id_scopes_the_sweep_to_one_tenant(self, db_session: Session):
        tenant_a = make_tenant(db_session, name="Tenant A")
        tenant_b = make_tenant(db_session, name="Tenant B")
        receptionist_a, _ = make_receptionist(db_session, tenant=tenant_a)
        receptionist_b, _ = make_receptionist(db_session, tenant=tenant_b)
        _make_conversation(db_session, tenant=tenant_a, receptionist=receptionist_a, last_message_minutes_ago=120)
        _make_conversation(db_session, tenant=tenant_b, receptionist=receptionist_b, last_message_minutes_ago=120)

        result = sweep_stale_conversations(db_session, stale_after_minutes=60, batch_limit=100, tenant_id=tenant_a.id)
        assert result.scanned == 1

    def test_batch_limit_is_hard_capped_regardless_of_caller_input(self, db_session: Session):
        tenant = make_tenant(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        _make_conversation(db_session, tenant=tenant, receptionist=receptionist, last_message_minutes_ago=120)
        # Absurdly large requested batch limit must still be clamped — this
        # only proves the clamp doesn't error; a real 500+ row scan isn't
        # exercised here, that would be excessive for a unit test.
        result = sweep_stale_conversations(db_session, stale_after_minutes=60, batch_limit=10_000)
        assert result.scanned == 1
