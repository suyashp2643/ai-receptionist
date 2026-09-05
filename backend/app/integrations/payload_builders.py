"""Builds event payloads (app/integrations/envelope.py) from ORM rows.
Kept separate from the services that call it so every producing service
(contact_service, enquiry_service, appointment_request_service,
human_handoff_service, the conversation orchestrator) constructs its
payload the same way, rather than each re-deriving the PII/consent policy
inline. See envelope.py's own docstring for that policy."""

from __future__ import annotations

import uuid

from app.integrations.envelope import (
    AppointmentRequestCreatedPayload,
    AppointmentRequestStatusChangedPayload,
    ContactCapturedPayload,
    ContactSummaryPayload,
    ConversationAbandonedPayload,
    ConversationCompletedPayload,
    EnquiryCreatedPayload,
    EnquiryQualifiedPayload,
    EnquiryStatusChangedPayload,
    HumanHandoffRequestedPayload,
    HumanHandoffStatusChangedPayload,
    SafetyEscalationDetectedPayload,
)
from app.models.appointment_request import AppointmentRequest
from app.models.contact import Contact
from app.models.enquiry import Enquiry
from app.models.human_handoff import HumanHandoff


def contact_summary(contact: Contact | None) -> ContactSummaryPayload | None:
    if contact is None:
        return None
    return ContactSummaryPayload(
        contact_id=contact.id,
        name=contact.name,
        normalized_email=contact.normalized_email,
        normalized_phone=contact.normalized_phone,
        preferred_contact_method=contact.preferred_contact_method.value if contact.preferred_contact_method else None,
        marketing_consent=contact.marketing_consent,
        source=contact.source,
    )


def contact_captured(contact: Contact) -> ContactCapturedPayload:
    summary = contact_summary(contact)
    assert summary is not None  # contact is never None here; narrows the type for mypy
    return ContactCapturedPayload(contact=summary, conversation_id=contact.conversation_id)


def enquiry_created(enquiry: Enquiry, *, contact: Contact | None) -> EnquiryCreatedPayload:
    return EnquiryCreatedPayload(
        enquiry_id=enquiry.id,
        receptionist_id=enquiry.receptionist_id,
        conversation_id=enquiry.conversation_id,
        contact=contact_summary(contact),
        status=enquiry.status.value,
        source=enquiry.source,
        qualification_complete=enquiry.qualification_complete,
    )


def enquiry_qualified(enquiry: Enquiry, *, contact: Contact | None) -> EnquiryQualifiedPayload:
    return EnquiryQualifiedPayload(
        enquiry_id=enquiry.id,
        receptionist_id=enquiry.receptionist_id,
        conversation_id=enquiry.conversation_id,
        contact=contact_summary(contact),
        status=enquiry.status.value,
        qualification_data=enquiry.qualification_data,
        recommended_next_action=enquiry.recommended_next_action,
    )


def enquiry_status_changed(enquiry: Enquiry, *, previous_status: str) -> EnquiryStatusChangedPayload:
    return EnquiryStatusChangedPayload(
        enquiry_id=enquiry.id,
        receptionist_id=enquiry.receptionist_id,
        previous_status=previous_status,
        new_status=enquiry.status.value,
    )


def appointment_request_created(
    request: AppointmentRequest, *, contact: Contact | None
) -> AppointmentRequestCreatedPayload:
    return AppointmentRequestCreatedPayload(
        appointment_request_id=request.id,
        receptionist_id=request.receptionist_id,
        conversation_id=request.conversation_id,
        contact=contact_summary(contact),
        requested_date=request.requested_date.isoformat(),
        requested_time=request.requested_time.isoformat() if request.requested_time else None,
        requested_time_window=request.requested_time_window,
        timezone=request.timezone,
        notes=request.notes,
        location_id=request.location_id,
        service_id=request.service_id,
        status=request.status.value,
    )


def appointment_request_status_changed(
    request: AppointmentRequest, *, previous_status: str
) -> AppointmentRequestStatusChangedPayload:
    return AppointmentRequestStatusChangedPayload(
        appointment_request_id=request.id,
        receptionist_id=request.receptionist_id,
        previous_status=previous_status,
        new_status=request.status.value,
    )


def human_handoff_requested(handoff: HumanHandoff, *, contact: Contact | None) -> HumanHandoffRequestedPayload:
    return HumanHandoffRequestedPayload(
        handoff_id=handoff.id,
        receptionist_id=handoff.receptionist_id,
        conversation_id=handoff.conversation_id,
        contact=contact_summary(contact),
        reason=handoff.reason,
        urgency=handoff.urgency,
        preferred_contact_method=handoff.preferred_contact_method.value if handoff.preferred_contact_method else None,
        status=handoff.status.value,
    )


def human_handoff_status_changed(handoff: HumanHandoff, *, previous_status: str) -> HumanHandoffStatusChangedPayload:
    return HumanHandoffStatusChangedPayload(
        handoff_id=handoff.id,
        receptionist_id=handoff.receptionist_id,
        previous_status=previous_status,
        new_status=handoff.status.value,
    )


def conversation_completed(
    *, conversation_id: uuid.UUID, receptionist_id: uuid.UUID, mode: str, channel: str, message_count: int
) -> ConversationCompletedPayload:
    return ConversationCompletedPayload(
        conversation_id=conversation_id,
        receptionist_id=receptionist_id,
        mode=mode,
        channel=channel,
        message_count=message_count,
    )


def conversation_abandoned(
    *, conversation_id: uuid.UUID, receptionist_id: uuid.UUID, mode: str, channel: str, message_count: int
) -> ConversationAbandonedPayload:
    return ConversationAbandonedPayload(
        conversation_id=conversation_id,
        receptionist_id=receptionist_id,
        mode=mode,
        channel=channel,
        message_count=message_count,
    )


def safety_escalation_detected(
    *, conversation_id: uuid.UUID, receptionist_id: uuid.UUID, category: str, channel: str
) -> SafetyEscalationDetectedPayload:
    return SafetyEscalationDetectedPayload(
        conversation_id=conversation_id, receptionist_id=receptionist_id, category=category, channel=channel
    )
