import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AppointmentRequestStatus,
    EnquiryStatus,
    HandoffStatus,
    PreferredContactMethod,
)


class ContactListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str | None
    normalized_email: str | None
    normalized_phone: str | None
    preferred_contact_method: PreferredContactMethod | None
    source: str
    marketing_consent: bool
    created_at: datetime
    updated_at: datetime


class ContactListResponse(BaseModel):
    items: list[ContactListItem]
    total: int
    limit: int
    offset: int


class ContactDetailResponse(BaseModel):
    id: uuid.UUID
    name: str | None
    normalized_email: str | None
    normalized_phone: str | None
    preferred_contact_method: PreferredContactMethod | None
    marketing_consent: bool
    consent_captured_at: datetime | None
    source: str
    created_at: datetime
    updated_at: datetime
    conversation_ids: list[uuid.UUID]
    enquiry_ids: list[uuid.UUID]
    appointment_request_ids: list[uuid.UUID]
    handoff_ids: list[uuid.UUID]


class EnquiryListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contact_id: uuid.UUID | None
    receptionist_id: uuid.UUID
    source: str
    status: EnquiryStatus
    qualification_complete: bool
    recommended_next_action: str | None
    created_at: datetime
    updated_at: datetime
    version: int


class EnquiryListResponse(BaseModel):
    items: list[EnquiryListItem]
    total: int
    limit: int
    offset: int


class EnquiryDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
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
    version: int


class EnquiryStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: EnquiryStatus
    expected_version: int = Field(ge=1)


class AppointmentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contact_id: uuid.UUID | None
    receptionist_id: uuid.UUID
    location_id: uuid.UUID | None
    service_id: uuid.UUID | None
    requested_date: date
    requested_time: time | None
    requested_time_window: str | None
    timezone: str
    status: AppointmentRequestStatus
    created_at: datetime
    updated_at: datetime
    version: int


class AppointmentListResponse(BaseModel):
    items: list[AppointmentListItem]
    total: int
    limit: int
    offset: int


class AppointmentDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contact_id: uuid.UUID | None
    conversation_id: uuid.UUID
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
    version: int


class AppointmentStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: AppointmentRequestStatus
    expected_version: int = Field(ge=1)


class HandoffListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contact_id: uuid.UUID | None
    receptionist_id: uuid.UUID
    reason: str
    urgency: str | None
    preferred_contact_method: PreferredContactMethod | None
    status: HandoffStatus
    assigned_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    version: int


class HandoffListResponse(BaseModel):
    items: list[HandoffListItem]
    total: int
    limit: int
    offset: int


class HandoffDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contact_id: uuid.UUID | None
    conversation_id: uuid.UUID
    receptionist_id: uuid.UUID
    reason: str
    urgency: str | None
    preferred_contact_method: PreferredContactMethod | None
    status: HandoffStatus
    assigned_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    version: int
    is_clinic_emergency: bool = False


class HandoffStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: HandoffStatus
    expected_version: int = Field(ge=1)
