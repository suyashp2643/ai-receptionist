import uuid
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.core.security import create_access_token
from app.models.conversation import Conversation
from app.models.conversation_message import ConversationMessage
from app.models.enums import (
    ConversationChannel,
    ConversationMessageRole,
    ConversationMode,
    ConversationStatus,
)
from app.models.widget_installation import WidgetInstallation
from app.models.widget_visitor_session import WidgetVisitorSession
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import make_receptionist, make_tenant_with_owner

settings = get_settings()


def _auth_headers(user) -> dict[str, str]:
    token, _ = create_access_token(settings=settings, user_id=user.id, session_id=uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


def _make_conversation(db, *, tenant_id, receptionist_id, mode=ConversationMode.WIDGET, **overrides) -> Conversation:
    conv = Conversation(
        tenant_id=tenant_id,
        receptionist_id=receptionist_id,
        mode=mode,
        channel=ConversationChannel.WIDGET if mode == ConversationMode.WIDGET else ConversationChannel.DASHBOARD_TEST,
        provider="mock",
        status=overrides.pop("status", ConversationStatus.ACTIVE),
        started_at=overrides.pop("started_at", datetime.now(UTC)),
        **overrides,
    )
    db.add(conv)
    db.flush()
    return conv


def _make_session(db, *, tenant_id, receptionist_id, conversation_id, is_platform_preview=False):
    installation = WidgetInstallation(tenant_id=tenant_id, receptionist_id=receptionist_id)
    db.add(installation)
    db.flush()
    session = WidgetVisitorSession(
        tenant_id=tenant_id,
        widget_installation_id=installation.id,
        conversation_id=conversation_id,
        token_hash=uuid.uuid4().hex,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        is_platform_preview=is_platform_preview,
    )
    db.add(session)
    db.flush()
    return session


class TestListConversations:
    def test_lists_conversations_for_tenant(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        _make_session(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id, conversation_id=conv.id)

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/conversations", headers=_auth_headers(owner)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == str(conv.id)
        assert body["items"][0]["source"] == "widget"

    def test_source_filter(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id, mode=ConversationMode.TEST)
        widget_conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        _make_session(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id, conversation_id=widget_conv.id)

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/conversations",
            params={"source": "widget"},
            headers=_auth_headers(owner),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == str(widget_conv.id)

    def test_invalid_sort_column_rejected(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/conversations",
            params={"sort": "provider"},
            headers=_auth_headers(owner),
        )
        assert response.status_code == 422

    def test_pagination_is_bounded(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/conversations",
            params={"limit": 10_000},
            headers=_auth_headers(owner),
        )
        assert response.status_code == 422

    def test_cross_tenant_conversations_never_appear(self, db_backed_client: TestClient, db_session: Session):
        tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, _, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        receptionist_b, _ = make_receptionist(db_session, tenant=tenant_b)
        _make_conversation(db_session, tenant_id=tenant_b.id, receptionist_id=receptionist_b.id)

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant_a.id}/conversations", headers=_auth_headers(owner_a)
        )
        assert response.status_code == 200
        assert response.json()["total"] == 0

    def test_non_member_gets_404_not_403(self, db_backed_client: TestClient, db_session: Session):
        tenant_a, _, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        _, outsider, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant_a.id}/conversations", headers=_auth_headers(outsider)
        )
        assert response.status_code == 404


class TestConversationDetail:
    def test_detail_includes_messages_and_linked_records(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        _make_session(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id, conversation_id=conv.id)
        db_session.add(
            ConversationMessage(
                tenant_id=tenant.id,
                conversation_id=conv.id,
                role=ConversationMessageRole.USER,
                content="Hello",
                sequence_number=0,
            )
        )
        db_session.flush()

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/conversations/{conv.id}", headers=_auth_headers(owner)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["source"] == "widget"
        assert len(body["messages"]) == 1
        assert body["messages"][0]["content"] == "Hello"
        assert "system_prompt" not in body
        assert "provider_api_key" not in str(body)
        assert "capability_token" not in str(body)
        assert "token_hash" not in str(body)

    def test_clinic_emergency_flag_is_surfaced(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        conv.had_safety_event = True
        conv.had_clinic_emergency = True
        db_session.flush()

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/conversations/{conv.id}", headers=_auth_headers(owner)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["had_clinic_emergency"] is True
        assert body["had_safety_event"] is True

    def test_cross_tenant_detail_is_404(self, db_backed_client: TestClient, db_session: Session):
        tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="Tenant A")
        tenant_b, _, _ = make_tenant_with_owner(db_session, tenant_name="Tenant B")
        receptionist_b, _ = make_receptionist(db_session, tenant=tenant_b)
        conv_b = _make_conversation(db_session, tenant_id=tenant_b.id, receptionist_id=receptionist_b.id)

        response = db_backed_client.get(
            f"/api/v1/tenants/{tenant_a.id}/conversations/{conv_b.id}", headers=_auth_headers(owner_a)
        )
        assert response.status_code == 404
