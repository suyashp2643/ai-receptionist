"""Maintains one Enquiry row per widget conversation as a durable,
tenant-reviewable snapshot of qualification progress — separate from
Conversation.collected_data (Phase 4) so a tenant has a stable local record
even if the conversation itself is later pruned. Local-only: never synced
to Revenue Brain or any external CRM in Phase 5."""

import uuid

from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.enquiry import Enquiry
from app.repositories.enquiry import EnquiryRepository


def upsert_enquiry_from_conversation(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    conversation: Conversation,
    contact_id: uuid.UUID | None = None,
    recommended_next_action: str | None = None,
    source: str = "widget",
) -> Enquiry:
    repo = EnquiryRepository(db, tenant_id)
    enquiry = repo.get_by_conversation_id(conversation.id)

    if enquiry is None:
        enquiry = Enquiry(
            tenant_id=tenant_id,
            receptionist_id=conversation.receptionist_id,
            conversation_id=conversation.id,
            contact_id=contact_id,
            source=source,
            qualification_data=dict(conversation.collected_data),
            qualification_complete=conversation.qualification_complete,
            recommended_next_action=recommended_next_action,
        )
        repo.add(enquiry)
    else:
        enquiry.qualification_data = dict(conversation.collected_data)
        enquiry.qualification_complete = conversation.qualification_complete
        if recommended_next_action is not None:
            enquiry.recommended_next_action = recommended_next_action
        if contact_id is not None:
            enquiry.contact_id = contact_id

    db.flush()
    return enquiry
