"""Human handoff REQUEST creation for the public widget. Records a request
only — nothing here calls, messages, or notifies anyone (see HumanHandoff's
docstring), and this must never be reachable in place of, or presented as,
the safety engine's emergency-guidance response (app/ai/safety.py). The
orchestrator always evaluates safety independently before any widget action
flow runs; this service has no knowledge of, and does not gate, that check.

Phase 6 adds the dashboard's claim/resolve/cancel workflow. `claim()` is the
ONLY path that may move a handoff from OPEN to CLAIMED — it uses a single
atomic conditional UPDATE (see HumanHandoffRepository.claim_atomically) so
two tenant members clicking "claim" at the same moment can never both
succeed. `update_status()` (resolve/cancel) deliberately refuses to accept
CLAIMED as a target for exactly this reason — routing that transition
through here would reintroduce the read-then-write race claim() exists to
avoid."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.enums import HandoffStatus, PreferredContactMethod
from app.models.human_handoff import HumanHandoff
from app.repositories.human_handoff import HumanHandoffRepository
from app.services import activity_service
from app.services.concurrency import apply_versioned_update

HANDOFF_STATUS_TRANSITIONS: dict[HandoffStatus, frozenset[HandoffStatus]] = {
    HandoffStatus.OPEN: frozenset({HandoffStatus.CANCELLED}),
    HandoffStatus.CLAIMED: frozenset({HandoffStatus.RESOLVED, HandoffStatus.CANCELLED}),
    HandoffStatus.RESOLVED: frozenset(),
    HandoffStatus.CANCELLED: frozenset(),
}


class InvalidHandoffStatusTransitionError(Exception):
    pass


class HandoffAlreadyClaimedError(Exception):
    """Raised by claim() when the atomic conditional UPDATE matched zero
    rows — either someone else already claimed it, or it is no longer
    OPEN (e.g. already cancelled). Deliberately one error for both cases:
    the caller only needs to know "you didn't get it," not why."""


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


def claim(db: Session, *, tenant_id: uuid.UUID, actor_user_id: uuid.UUID, handoff_id: uuid.UUID) -> HumanHandoff:
    """Atomically claims an OPEN handoff for `actor_user_id`. Raises
    HandoffAlreadyClaimedError if the atomic UPDATE matched no row."""
    repo = HumanHandoffRepository(db, tenant_id)
    won = repo.claim_atomically(handoff_id, actor_user_id=actor_user_id)
    if not won:
        raise HandoffAlreadyClaimedError("This handoff is no longer open.")

    handoff = repo.get(handoff_id)
    assert handoff is not None  # the UPDATE above just matched this row
    activity_service.record(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action_type="handoff.claimed",
        entity_type="human_handoff",
        entity_id=handoff.id,
        metadata={"from": HandoffStatus.OPEN.value, "to": HandoffStatus.CLAIMED.value},
    )
    db.flush()
    return handoff


def update_status(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    handoff: HumanHandoff,
    new_status: HandoffStatus,
    expected_version: int,
) -> HumanHandoff:
    """Resolve or cancel — never claim (see this module's docstring; use
    `claim()` for OPEN -> CLAIMED). Raises InvalidHandoffStatusTransitionError
    (422) or VersionConflictError (409)."""
    current = handoff.status
    if new_status == HandoffStatus.CLAIMED:
        raise InvalidHandoffStatusTransitionError("Use the claim action to move a handoff to 'claimed'.")
    if new_status == current:
        raise InvalidHandoffStatusTransitionError(f"Handoff is already '{current.value}'.")
    allowed = HANDOFF_STATUS_TRANSITIONS.get(current, frozenset())
    if new_status not in allowed:
        raise InvalidHandoffStatusTransitionError(
            f"Cannot move a handoff from '{current.value}' to '{new_status.value}'."
        )

    values: dict = {"status": new_status}
    if new_status == HandoffStatus.RESOLVED:
        values["resolved_at"] = datetime.now(UTC)

    apply_versioned_update(db, handoff, expected_version=expected_version, values=values)
    activity_service.record(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action_type=f"handoff.{new_status.value}",
        entity_type="human_handoff",
        entity_id=handoff.id,
        metadata={"from": current.value, "to": new_status.value},
    )
    db.flush()
    return handoff
