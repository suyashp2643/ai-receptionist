import uuid

from app.config import get_settings
from app.core.security import create_access_token
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.enums import ConversationChannel, ConversationMode, TenantMemberRole
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


class TestNoteCreation:
    def test_create_note_on_own_tenant_entity(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)

        response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/notes",
            json={"entity_type": "conversation", "entity_id": str(conv.id), "body": "Called back, left voicemail."},
            headers=_auth_headers(owner),
        )
        assert response.status_code == 201
        assert response.json()["body"] == "Called back, left voicemail."

    def test_cannot_attach_note_to_another_tenants_entity(self, db_backed_client: TestClient, db_session: Session):
        tenant_a, owner_a, _ = make_tenant_with_owner(db_session, tenant_name="A")
        tenant_b, _, _ = make_tenant_with_owner(db_session, tenant_name="B")
        receptionist_b, _ = make_receptionist(db_session, tenant=tenant_b)
        conv_b = _make_conversation(db_session, tenant_id=tenant_b.id, receptionist_id=receptionist_b.id)

        response = db_backed_client.post(
            f"/api/v1/tenants/{tenant_a.id}/notes",
            json={"entity_type": "conversation", "entity_id": str(conv_b.id), "body": "Cross-tenant attempt"},
            headers=_auth_headers(owner_a),
        )
        assert response.status_code == 404

    def test_cannot_attach_note_to_nonexistent_entity(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/notes",
            json={"entity_type": "contact", "entity_id": str(uuid.uuid4()), "body": "No such contact"},
            headers=_auth_headers(owner),
        )
        assert response.status_code == 404

    def test_empty_body_is_rejected(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        conv = _make_conversation(db_session, tenant_id=tenant.id, receptionist_id=receptionist.id)
        response = db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/notes",
            json={"entity_type": "conversation", "entity_id": str(conv.id), "body": "   "},
            headers=_auth_headers(owner),
        )
        assert response.status_code == 422

    def test_notes_are_isolated_per_entity_and_tenant(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        receptionist, _ = make_receptionist(db_session, tenant=tenant)
        contact = Contact(tenant_id=tenant.id, name="Pat")
        db_session.add(contact)
        db_session.flush()

        db_backed_client.post(
            f"/api/v1/tenants/{tenant.id}/notes",
            json={"entity_type": "contact", "entity_id": str(contact.id), "body": "Note one"},
            headers=_auth_headers(owner),
        )

        list_response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/notes",
            params={"entity_type": "contact", "entity_id": str(contact.id)},
            headers=_auth_headers(owner),
        )
        assert list_response.status_code == 200
        assert len(list_response.json()) == 1


class TestNoteEditAndDelete:
    def _create_note(self, client, tenant, headers, contact_id):
        response = client.post(
            f"/api/v1/tenants/{tenant.id}/notes",
            json={"entity_type": "contact", "entity_id": str(contact_id), "body": "Original"},
            headers=headers,
        )
        return response.json()["id"]

    def test_only_author_can_edit(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        contact = Contact(tenant_id=tenant.id, name="Pat")
        db_session.add(contact)
        db_session.flush()
        note_id = self._create_note(db_backed_client, tenant, _auth_headers(owner), contact.id)

        other_member = make_user(db_session)
        add_member(db_session, tenant=tenant, user=other_member, role=TenantMemberRole.MEMBER)

        response = db_backed_client.patch(
            f"/api/v1/tenants/{tenant.id}/notes/{note_id}",
            json={"body": "Edited by someone else"},
            headers=_auth_headers(other_member),
        )
        assert response.status_code == 403

    def test_author_can_delete_own_note(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        contact = Contact(tenant_id=tenant.id, name="Pat")
        db_session.add(contact)
        db_session.flush()
        note_id = self._create_note(db_backed_client, tenant, _auth_headers(owner), contact.id)

        response = db_backed_client.delete(f"/api/v1/tenants/{tenant.id}/notes/{note_id}", headers=_auth_headers(owner))
        assert response.status_code == 204

        list_response = db_backed_client.get(
            f"/api/v1/tenants/{tenant.id}/notes",
            params={"entity_type": "contact", "entity_id": str(contact.id)},
            headers=_auth_headers(owner),
        )
        assert list_response.json() == []

    def test_admin_can_delete_a_members_note(self, db_backed_client: TestClient, db_session: Session):
        tenant, owner, _ = make_tenant_with_owner(db_session)
        contact = Contact(tenant_id=tenant.id, name="Pat")
        db_session.add(contact)
        db_session.flush()
        member_user = make_user(db_session)
        add_member(db_session, tenant=tenant, user=member_user, role=TenantMemberRole.MEMBER)
        note_id = self._create_note(db_backed_client, tenant, _auth_headers(member_user), contact.id)

        response = db_backed_client.delete(f"/api/v1/tenants/{tenant.id}/notes/{note_id}", headers=_auth_headers(owner))
        assert response.status_code == 204

    def test_member_cannot_delete_another_members_note(self, db_backed_client: TestClient, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        contact = Contact(tenant_id=tenant.id, name="Pat")
        db_session.add(contact)
        db_session.flush()
        member_a = make_user(db_session)
        add_member(db_session, tenant=tenant, user=member_a, role=TenantMemberRole.MEMBER)
        member_b = make_user(db_session)
        add_member(db_session, tenant=tenant, user=member_b, role=TenantMemberRole.MEMBER)
        note_id = self._create_note(db_backed_client, tenant, _auth_headers(member_a), contact.id)

        response = db_backed_client.delete(
            f"/api/v1/tenants/{tenant.id}/notes/{note_id}", headers=_auth_headers(member_b)
        )
        assert response.status_code == 403
