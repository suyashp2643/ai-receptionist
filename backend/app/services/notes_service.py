"""Internal notes: staff-only annotations on one operational record. Never
read by the AI orchestrator, never served to the public widget — see
InternalNote's docstring.

`entity_type` must be validated against the exact same tenant-scoped
repository every other route uses for that resource, so a note can never be
attached to another tenant's row even though InternalNote's own foreign key
to e.g. `enquiries.id` is not itself tenant-composite (see
InternalNote's docstring for why a plain FK was still the right choice)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.internal_note import InternalNote
from app.repositories.appointment_request import AppointmentRequestRepository
from app.repositories.contact import ContactRepository
from app.repositories.conversation import ConversationRepository
from app.repositories.enquiry import EnquiryRepository
from app.repositories.human_handoff import HumanHandoffRepository
from app.repositories.internal_note import InternalNoteRepository
from app.services import activity_service

MAX_NOTE_BODY_LENGTH = 4000

_ENTITY_LOOKUPS = {
    "conversation": lambda db, tenant_id, entity_id: ConversationRepository(db, tenant_id).get(entity_id),
    "contact": lambda db, tenant_id, entity_id: ContactRepository(db, tenant_id).get(entity_id),
    "enquiry": lambda db, tenant_id, entity_id: EnquiryRepository(db, tenant_id).get(entity_id),
    "appointment_request": lambda db, tenant_id, entity_id: AppointmentRequestRepository(db, tenant_id).get(entity_id),
    "human_handoff": lambda db, tenant_id, entity_id: HumanHandoffRepository(db, tenant_id).get(entity_id),
}

_ENTITY_FK_FIELD = {
    "conversation": "conversation_id",
    "contact": "contact_id",
    "enquiry": "enquiry_id",
    "appointment_request": "appointment_request_id",
    "human_handoff": "human_handoff_id",
}


class UnknownNoteEntityError(Exception):
    """The referenced entity does not exist for this tenant — including a
    real entity belonging to a *different* tenant, which must be
    indistinguishable from "does not exist" (see docs/security.md's
    cross-tenant 404 convention)."""


class NoteBodyInvalidError(Exception):
    pass


class NoteNotFoundError(Exception):
    pass


class NotNoteAuthorError(Exception):
    pass


def _validate_body(body: str) -> str:
    stripped = body.strip()
    if not stripped:
        raise NoteBodyInvalidError("Note cannot be empty.")
    if len(stripped) > MAX_NOTE_BODY_LENGTH:
        raise NoteBodyInvalidError(f"Note is too long (max {MAX_NOTE_BODY_LENGTH} characters).")
    return stripped


def create_note(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    author_user_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    body: str,
) -> InternalNote:
    lookup = _ENTITY_LOOKUPS[entity_type]
    if lookup(db, tenant_id, entity_id) is None:
        raise UnknownNoteEntityError(f"No {entity_type.replace('_', ' ')} was found for this business.")

    note = InternalNote(
        tenant_id=tenant_id,
        author_user_id=author_user_id,
        body=_validate_body(body),
        **{_ENTITY_FK_FIELD[entity_type]: entity_id},
    )
    InternalNoteRepository(db, tenant_id).add(note)
    db.flush()
    activity_service.record(
        db,
        tenant_id=tenant_id,
        actor_user_id=author_user_id,
        action_type="note.created",
        entity_type=entity_type,
        entity_id=entity_id,
        metadata={"note_id": str(note.id)},
    )
    db.flush()
    return note


def update_note(
    db: Session, *, tenant_id: uuid.UUID, actor_user_id: uuid.UUID, note_id: uuid.UUID, body: str
) -> InternalNote:
    note = InternalNoteRepository(db, tenant_id).get_not_deleted(note_id)
    if note is None:
        raise NoteNotFoundError("Note not found.")
    if note.author_user_id != actor_user_id:
        raise NotNoteAuthorError("Only the author can edit this note.")
    note.body = _validate_body(body)
    db.flush()
    return note


def delete_note(
    db: Session, *, tenant_id: uuid.UUID, actor_user_id: uuid.UUID, note_id: uuid.UUID, is_admin_or_owner: bool
) -> None:
    note = InternalNoteRepository(db, tenant_id).get_not_deleted(note_id)
    if note is None:
        raise NoteNotFoundError("Note not found.")
    if note.author_user_id != actor_user_id and not is_admin_or_owner:
        raise NotNoteAuthorError("Only the author, an admin, or the owner can delete this note.")

    entity_type = next(name for name, field in _ENTITY_FK_FIELD.items() if getattr(note, field) is not None)
    entity_id = getattr(note, _ENTITY_FK_FIELD[entity_type])

    note.deleted_at = datetime.now(UTC)
    activity_service.record(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action_type="note.deleted",
        entity_type=entity_type,
        entity_id=entity_id,
        metadata={"note_id": str(note.id)},
    )
    db.flush()
