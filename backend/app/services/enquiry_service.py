"""Maintains one Enquiry row per widget conversation as a durable,
tenant-reviewable snapshot of qualification progress — separate from
Conversation.collected_data (Phase 4) so a tenant has a stable local record
even if the conversation itself is later pruned. Local-only: never synced
to Revenue Brain or any external CRM in Phase 5.

Phase 6 adds `update_status`: a validated, version-checked pipeline status
transition. `WON`/`LOST` are manual operational labels a tenant applies to
describe an outcome — this system never calculates or infers revenue from
either, and no route anywhere computes a dollar amount from enquiry status.
`CLOSED` is a legacy status (see EnquiryStatus's docstring) treated as a
synonym of `ARCHIVED` in the transition graph — reachable and terminal in
exactly the same places, so old data does not become a dead end."""

import uuid

from sqlalchemy.orm import Session

from app.integrations import payload_builders
from app.integrations.envelope import EventType
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.enquiry import Enquiry
from app.models.enums import EnquiryStatus
from app.repositories.enquiry import EnquiryRepository
from app.services import activity_service, outbox_producer_service
from app.services.concurrency import apply_versioned_update

# The allowed pipeline: keys are current statuses, values are the set of
# statuses a PATCH may move *to* from there. Terminal statuses map to an
# empty set. `CLOSED` (legacy) is given the exact same edges as `ARCHIVED`
# so it behaves identically for any pre-Phase-6 row that still carries it.
_TERMINAL: frozenset[EnquiryStatus] = frozenset()
ENQUIRY_STATUS_TRANSITIONS: dict[EnquiryStatus, frozenset[EnquiryStatus]] = {
    EnquiryStatus.NEW: frozenset(
        {EnquiryStatus.QUALIFIED, EnquiryStatus.CONTACTED, EnquiryStatus.LOST, EnquiryStatus.ARCHIVED}
    ),
    EnquiryStatus.QUALIFIED: frozenset(
        {
            EnquiryStatus.CONTACTED,
            EnquiryStatus.APPOINTMENT_REQUESTED,
            EnquiryStatus.IN_PROGRESS,
            EnquiryStatus.WON,
            EnquiryStatus.LOST,
            EnquiryStatus.ARCHIVED,
        }
    ),
    EnquiryStatus.CONTACTED: frozenset(
        {
            EnquiryStatus.QUALIFIED,
            EnquiryStatus.APPOINTMENT_REQUESTED,
            EnquiryStatus.IN_PROGRESS,
            EnquiryStatus.WON,
            EnquiryStatus.LOST,
            EnquiryStatus.ARCHIVED,
        }
    ),
    EnquiryStatus.APPOINTMENT_REQUESTED: frozenset(
        {EnquiryStatus.IN_PROGRESS, EnquiryStatus.WON, EnquiryStatus.LOST, EnquiryStatus.ARCHIVED}
    ),
    EnquiryStatus.IN_PROGRESS: frozenset({EnquiryStatus.WON, EnquiryStatus.LOST, EnquiryStatus.ARCHIVED}),
    EnquiryStatus.WON: frozenset({EnquiryStatus.ARCHIVED}),
    EnquiryStatus.LOST: frozenset({EnquiryStatus.ARCHIVED}),
    EnquiryStatus.ARCHIVED: _TERMINAL,
    EnquiryStatus.CLOSED: frozenset({EnquiryStatus.ARCHIVED}),
}


class InvalidEnquiryStatusTransitionError(Exception):
    pass


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
    is_new = enquiry is None
    was_qualified = enquiry.qualification_complete if enquiry is not None else False

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

    # Phase 8 event production. Both checks fire at most once per enquiry's
    # lifetime (creation is a one-time transition by definition; the
    # qualification-completed check is gated on the False->True edge, not
    # "is currently complete", so a conversation that stays qualified across
    # many further turns never re-fires enquiry.qualified).
    if is_new or (not was_qualified and enquiry.qualification_complete):
        contact = db.get(Contact, enquiry.contact_id) if enquiry.contact_id else None
        if is_new:
            outbox_producer_service.produce_event(
                db,
                tenant_id=tenant_id,
                event_type=EventType.ENQUIRY_CREATED,
                payload=payload_builders.enquiry_created(enquiry, contact=contact),
                dedup_key=f"enquiry.created:{enquiry.id}",
                correlation_id=conversation.id,
            )
        if not was_qualified and enquiry.qualification_complete:
            outbox_producer_service.produce_event(
                db,
                tenant_id=tenant_id,
                event_type=EventType.ENQUIRY_QUALIFIED,
                payload=payload_builders.enquiry_qualified(enquiry, contact=contact),
                dedup_key=f"enquiry.qualified:{enquiry.id}",
                correlation_id=conversation.id,
            )

    return enquiry


def update_status(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    enquiry: Enquiry,
    new_status: EnquiryStatus,
    expected_version: int,
) -> Enquiry:
    """Validates the transition, applies it via a version-checked atomic
    UPDATE, and records an ActivityEvent with the old/new status pair —
    that event log is the actual status *history*; `version` only prevents
    a silent overwrite. Raises InvalidEnquiryStatusTransitionError (422) or
    VersionConflictError (409) — callers map these to HTTP responses."""
    current = enquiry.status
    if new_status == current:
        raise InvalidEnquiryStatusTransitionError(f"Enquiry is already '{current.value}'.")
    allowed = ENQUIRY_STATUS_TRANSITIONS.get(current, frozenset())
    if new_status not in allowed:
        raise InvalidEnquiryStatusTransitionError(
            f"Cannot move an enquiry from '{current.value}' to '{new_status.value}'."
        )

    apply_versioned_update(
        db,
        enquiry,
        expected_version=expected_version,
        values={"status": new_status},
    )
    activity_service.record(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action_type="enquiry.status_changed",
        entity_type="enquiry",
        entity_id=enquiry.id,
        metadata={"from": current.value, "to": new_status.value},
    )
    outbox_producer_service.produce_event(
        db,
        tenant_id=tenant_id,
        event_type=EventType.ENQUIRY_STATUS_CHANGED,
        payload=payload_builders.enquiry_status_changed(enquiry, previous_status=current.value),
        dedup_key=f"enquiry.status_changed:{enquiry.id}:{enquiry.version}",
    )
    db.flush()
    return enquiry
