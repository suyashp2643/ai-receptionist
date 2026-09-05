"""The versioned event contract every outbound integration event is built
from. This is the ONE place new outbound event types are named and their
payload shape fixed — see docs/integration-contracts.md for the full
policy write-up this module implements.

PII/consent/safety policy (enforced by construction, not by convention):
  - Every payload class below is a Pydantic model with `extra="forbid"` —
    a producer cannot accidentally leak an extra field by passing one; it
    is rejected at construction time, not silently dropped.
  - No payload includes a full conversation transcript, an internal staff
    note, a system prompt/instruction, a secret, or a credential. Where a
    conversation is referenced, only its id and small safe aggregates
    (message count, mode, channel) are included — never message content.
  - `ContactSummaryPayload.marketing_consent` is carried verbatim from
    Contact.marketing_consent and is NEVER defaulted to True, inferred
    from the contact's mere presence, or merged with any other consent
    concept — see app/models/contact.py's own docstring for why the
    codebase keeps this distinct. A receiver is responsible for honoring
    it; this module's only job is to never lie about it.
  - SafetyEscalationDetectedPayload carries a classification category
    (e.g. "clinic_urgent") and context ids only — never the message text
    that triggered it. See app/ai/safety.py.

Every event type is versioned independently (`event_version` starts at 1
per type) so a payload shape can change for one event type without forcing
every other type's consumers to re-validate.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

ENVELOPE_SCHEMA = "ai-receptionist.integration-event/v1"


class EventType(str, Enum):
    CONTACT_CAPTURED = "contact.captured"
    ENQUIRY_CREATED = "enquiry.created"
    ENQUIRY_QUALIFIED = "enquiry.qualified"
    ENQUIRY_STATUS_CHANGED = "enquiry.status_changed"
    APPOINTMENT_REQUEST_CREATED = "appointment_request.created"
    APPOINTMENT_REQUEST_STATUS_CHANGED = "appointment_request.status_changed"
    HUMAN_HANDOFF_REQUESTED = "human_handoff.requested"
    HUMAN_HANDOFF_STATUS_CHANGED = "human_handoff.status_changed"
    CONVERSATION_COMPLETED = "conversation.completed"
    CONVERSATION_ABANDONED = "conversation.abandoned"
    SAFETY_ESCALATION_DETECTED = "safety.escalation_detected"
    CONNECTION_TEST_EVENT = "connection.test_event"


# Every event type's current schema version. Bump the specific entry (never
# reuse a number for a changed shape) when that payload's fields change.
EVENT_TYPE_VERSIONS: dict[EventType, int] = dict.fromkeys(EventType, 1)


class BaseEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContactSummaryPayload(BaseEventPayload):
    """Embedded in event payloads that reference a contact. Never
    constructed for a contact the producer hasn't loaded — see
    app/integrations/payload_builders.py — so a missing contact is simply
    `None` on the parent payload, never a partially-filled placeholder."""

    contact_id: uuid.UUID
    name: str | None = None
    normalized_email: str | None = None
    normalized_phone: str | None = None
    preferred_contact_method: str | None = None
    marketing_consent: bool
    source: str


class ContactCapturedPayload(BaseEventPayload):
    contact: ContactSummaryPayload
    conversation_id: uuid.UUID | None = None


class EnquiryCreatedPayload(BaseEventPayload):
    enquiry_id: uuid.UUID
    receptionist_id: uuid.UUID
    conversation_id: uuid.UUID
    contact: ContactSummaryPayload | None = None
    status: str
    source: str
    qualification_complete: bool


class EnquiryQualifiedPayload(BaseEventPayload):
    enquiry_id: uuid.UUID
    receptionist_id: uuid.UUID
    conversation_id: uuid.UUID
    contact: ContactSummaryPayload | None = None
    status: str
    # The actual captured qualification answers — this is the substantive
    # lead payload the integration exists to deliver. Values come from
    # Enquiry.qualification_data, itself built only from the receptionist's
    # own configured qualification fields (see app/ai/tools) — never raw
    # unstructured transcript text.
    qualification_data: dict
    recommended_next_action: str | None = None


class EnquiryStatusChangedPayload(BaseEventPayload):
    enquiry_id: uuid.UUID
    receptionist_id: uuid.UUID
    previous_status: str
    new_status: str


class AppointmentRequestCreatedPayload(BaseEventPayload):
    appointment_request_id: uuid.UUID
    receptionist_id: uuid.UUID
    conversation_id: uuid.UUID
    contact: ContactSummaryPayload | None = None
    requested_date: str
    requested_time: str | None = None
    requested_time_window: str | None = None
    timezone: str
    notes: str | None = None
    location_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    status: str


class AppointmentRequestStatusChangedPayload(BaseEventPayload):
    appointment_request_id: uuid.UUID
    receptionist_id: uuid.UUID
    previous_status: str
    new_status: str


class HumanHandoffRequestedPayload(BaseEventPayload):
    handoff_id: uuid.UUID
    receptionist_id: uuid.UUID
    conversation_id: uuid.UUID
    contact: ContactSummaryPayload | None = None
    reason: str
    urgency: str | None = None
    preferred_contact_method: str | None = None
    status: str


class HumanHandoffStatusChangedPayload(BaseEventPayload):
    handoff_id: uuid.UUID
    receptionist_id: uuid.UUID
    previous_status: str
    new_status: str


class ConversationCompletedPayload(BaseEventPayload):
    conversation_id: uuid.UUID
    receptionist_id: uuid.UUID
    mode: str
    channel: str
    message_count: int


class ConversationAbandonedPayload(BaseEventPayload):
    conversation_id: uuid.UUID
    receptionist_id: uuid.UUID
    mode: str
    channel: str
    message_count: int


class SafetyEscalationDetectedPayload(BaseEventPayload):
    """Deliberately excludes the triggering message text — see this
    module's docstring. `category` is one of app/ai/safety.py's own
    SafetyDirective.category values (e.g. "clinic_urgent",
    "injection_attempt")."""

    conversation_id: uuid.UUID
    receptionist_id: uuid.UUID
    category: str
    channel: str


class ConnectionTestEventPayload(BaseEventPayload):
    """The only payload never produced from a real domain mutation — sent
    on demand by the "send test event" dashboard action and by the
    integration lab (see app/services/outbox_producer_service.py's
    `produce_test_event`)."""

    message: str = "Test event from the AI Receptionist integration lab."
    triggered_by: str


EVENT_PAYLOAD_TYPES: dict[EventType, type[BaseEventPayload]] = {
    EventType.CONTACT_CAPTURED: ContactCapturedPayload,
    EventType.ENQUIRY_CREATED: EnquiryCreatedPayload,
    EventType.ENQUIRY_QUALIFIED: EnquiryQualifiedPayload,
    EventType.ENQUIRY_STATUS_CHANGED: EnquiryStatusChangedPayload,
    EventType.APPOINTMENT_REQUEST_CREATED: AppointmentRequestCreatedPayload,
    EventType.APPOINTMENT_REQUEST_STATUS_CHANGED: AppointmentRequestStatusChangedPayload,
    EventType.HUMAN_HANDOFF_REQUESTED: HumanHandoffRequestedPayload,
    EventType.HUMAN_HANDOFF_STATUS_CHANGED: HumanHandoffStatusChangedPayload,
    EventType.CONVERSATION_COMPLETED: ConversationCompletedPayload,
    EventType.CONVERSATION_ABANDONED: ConversationAbandonedPayload,
    EventType.SAFETY_ESCALATION_DETECTED: SafetyEscalationDetectedPayload,
    EventType.CONNECTION_TEST_EVENT: ConnectionTestEventPayload,
}


class EventEnvelope(BaseModel):
    """The wire shape every outbound event is serialized as. `data` is
    always an already-validated instance of that event type's payload
    class (see EVENT_PAYLOAD_TYPES) — construction goes through
    `build_envelope` below, never assembled ad hoc, so the pairing between
    `event_type`/`event_version` and the shape of `data` can never drift."""

    model_config = ConfigDict(extra="forbid")

    schema_: str = Field(default=ENVELOPE_SCHEMA, alias="schema")
    event_id: uuid.UUID
    event_type: EventType
    event_version: int
    occurred_at: datetime
    tenant_reference: str
    source: str = "ai-receptionist"
    correlation_id: uuid.UUID | None = None
    causation_id: uuid.UUID | None = None
    data: dict
    metadata: dict = Field(default_factory=dict)


def build_envelope(
    event_type: EventType,
    *,
    tenant_id: uuid.UUID,
    payload: BaseEventPayload,
    correlation_id: uuid.UUID | None = None,
    causation_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> EventEnvelope:
    """The only supported way to construct an EventEnvelope. Raises
    TypeError if `payload` is not an instance of the exact payload class
    registered for `event_type` in EVENT_PAYLOAD_TYPES — a producer
    passing the wrong payload type for an event type is a programming
    error, not something to coerce or silently accept."""
    expected_type = EVENT_PAYLOAD_TYPES[event_type]
    if type(payload) is not expected_type:
        raise TypeError(
            f"{event_type.value} events must carry a {expected_type.__name__} payload, got {type(payload).__name__}."
        )
    return EventEnvelope(
        event_id=uuid.uuid4(),
        event_type=event_type,
        event_version=EVENT_TYPE_VERSIONS[event_type],
        occurred_at=datetime.now(UTC),
        tenant_reference=str(tenant_id),
        correlation_id=correlation_id,
        causation_id=causation_id,
        data=payload.model_dump(mode="json"),
        metadata=metadata or {},
    )
