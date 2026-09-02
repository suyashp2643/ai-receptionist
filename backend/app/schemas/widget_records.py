"""Minimal, read-only dashboard views over Phase 5's captured records
(Contact, Enquiry, AppointmentRequest, HumanHandoff). This is deliberately
NOT the full analytics/CRM dashboard — that is Phase 6 scope. Phase 5 only
needs enough visibility for a tenant to verify that a widget conversation's
contact info, enquiry, appointment request, or handoff request actually
landed in their own tenant-owned records."""

import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    AppointmentRequestStatus,
    EnquiryStatus,
    HandoffStatus,
    PreferredContactMethod,
)


class ContactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID | None
    name: str | None
    normalized_email: str | None
    normalized_phone: str | None
    preferred_contact_method: PreferredContactMethod | None
    marketing_consent: bool
    consent_captured_at: datetime | None
    source: str
    created_at: datetime
    updated_at: datetime


class EnquiryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    contact_id: uuid.UUID | None
    conversation_id: uuid.UUID
    receptionist_id: uuid.UUID
    source: str
    status: EnquiryStatus
    qualification_data: dict
    qualification_complete: bool
    recommended_next_action: str | None
    created_at: datetime
    updated_at: datetime


class AppointmentRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    contact_id: uuid.UUID | None
    receptionist_id: uuid.UUID
    location_id: uuid.UUID | None
    service_id: uuid.UUID | None
    requested_date: date
    requested_time: time | None
    requested_time_window: str | None
    timezone: str
    notes: str | None
    status: AppointmentRequestStatus
    created_at: datetime
    updated_at: datetime


class HumanHandoffRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    contact_id: uuid.UUID | None
    receptionist_id: uuid.UUID
    reason: str
    urgency: str | None
    preferred_contact_method: PreferredContactMethod | None
    status: HandoffStatus
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
