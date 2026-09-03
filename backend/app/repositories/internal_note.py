import uuid
from collections.abc import Sequence

from sqlalchemy import select

from app.models.internal_note import InternalNote
from app.repositories.base import TenantScopedRepository

_ENTITY_COLUMNS = {
    "conversation": InternalNote.conversation_id,
    "contact": InternalNote.contact_id,
    "enquiry": InternalNote.enquiry_id,
    "appointment_request": InternalNote.appointment_request_id,
    "human_handoff": InternalNote.human_handoff_id,
}


class InternalNoteRepository(TenantScopedRepository[InternalNote]):  # type: ignore[type-var]
    model = InternalNote

    def list_for_entity(self, entity_type: str, entity_id: uuid.UUID) -> Sequence[InternalNote]:
        column = _ENTITY_COLUMNS[entity_type]
        stmt = (
            select(InternalNote)
            .where(
                InternalNote.tenant_id == self.tenant_id,
                column == entity_id,
                InternalNote.deleted_at.is_(None),
            )
            .order_by(InternalNote.created_at.desc())
        )
        return self.db.scalars(stmt).all()

    def get_not_deleted(self, note_id: uuid.UUID) -> InternalNote | None:
        stmt = select(InternalNote).where(
            InternalNote.id == note_id,
            InternalNote.tenant_id == self.tenant_id,
            InternalNote.deleted_at.is_(None),
        )
        return self.db.scalars(stmt).first()
