"""Human handoff REQUEST creation for the public widget. Records a request
only — nothing here calls, messages, or notifies anyone (see HumanHandoff's
docstring), and this must never be reachable in place of, or presented as,
the safety engine's emergency-guidance response (app/ai/safety.py). The
orchestrator always evaluates safety independently before any widget action
flow runs; this service has no knowledge of, and does not gate, that check."""

import uuid

from sqlalchemy.orm import Session

from app.models.enums import HandoffStatus, PreferredContactMethod
from app.models.human_handoff import HumanHandoff
from app.repositories.human_handoff import HumanHandoffRepository


def create_handoff_request(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    receptionist_id: uuid.UUID,
    conversation_id: uuid.UUID,
    contact_id: uuid.UUID | None,
    reason: str,
    urgency: str | None,
    preferred_contact_method: PreferredContactMethod | None,
    idempotency_key: str | None,
) -> HumanHandoff:
    repo = HumanHandoffRepository(db, tenant_id)

    if idempotency_key:
        existing = repo.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing

    # Repeated-click protection even without an idempotency key: a
    # conversation that already has an OPEN handoff gets that one returned
    # rather than a second row, since a visitor mashing "request a
    # callback" a few times means "I really want a callback", not "I want
    # five callbacks".
    for existing_handoff in repo.list_by_conversation_id(conversation_id):
        if existing_handoff.status == HandoffStatus.OPEN:
            return existing_handoff

    handoff = HumanHandoff(
        tenant_id=tenant_id,
        receptionist_id=receptionist_id,
        conversation_id=conversation_id,
        contact_id=contact_id,
        reason=reason,
        urgency=urgency,
        preferred_contact_method=preferred_contact_method,
        idempotency_key=idempotency_key,
    )
    repo.add(handoff)
    db.flush()
    return handoff
