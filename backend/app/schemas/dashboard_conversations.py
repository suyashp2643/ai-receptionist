import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.core.conversation_source import ConversationSource
from app.models.enums import ConversationStatus
from app.schemas.conversation import ConversationMessageRead, ConversationSummaryRead

# Never exposed here or anywhere else in this schema: system prompt text,
# provider API keys/secrets, capability tokens or their hashes, or another
# tenant's data — see ConversationMessageRead (reused as-is from Phase 4),
# which already omits all of these.


class ConversationListItem(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: uuid.UUID
    receptionist_id: uuid.UUID
    started_at: datetime
    last_message_at: datetime | None
    status: ConversationStatus
    source: ConversationSource
    visitor_reference: str | None
    qualification_complete: bool
    had_safety_event: bool
    had_clinic_emergency: bool
    message_count: int | None = None
    has_appointment_request: bool | None = None
    has_handoff: bool | None = None


class ConversationListResponse(BaseModel):
    items: list[ConversationListItem]
    total: int
    limit: int
    offset: int


class ConversationDetailContact(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str | None
    normalized_email: str | None
    normalized_phone: str | None


class ConversationDetailEnquiry(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: str


class ConversationDetailAppointment(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: str
    requested_date: date


class ConversationDetailHandoff(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: str


class ConversationDashboardDetailResponse(BaseModel):
    id: uuid.UUID
    receptionist_id: uuid.UUID
    source: ConversationSource
    status: ConversationStatus
    provider: str
    locale: str
    started_at: datetime
    last_message_at: datetime | None
    completed_at: datetime | None
    qualification_complete: bool
    collected_data: dict
    had_safety_event: bool
    had_clinic_emergency: bool
    messages: list[ConversationMessageRead]
    message_total: int
    message_limit: int
    message_offset: int
    summary: ConversationSummaryRead | None
    contact: ConversationDetailContact | None
    enquiry: ConversationDetailEnquiry | None
    appointment_requests: list[ConversationDetailAppointment]
    handoffs: list[ConversationDetailHandoff]


CONVERSATION_SORT_ALLOWLIST = frozenset({"started_at", "last_message_at"})
