"""Every schema in this module is what a public, unauthenticated (beyond a
visitor capability token) caller may see or send. None of these may ever
gain a `tenant_id`, `receptionist_id`, internal id list, system prompt,
private knowledge content, or any other field from the "must never expose"
list in docs/security.md — that boundary is enforced by these schemas only
including the fields below, not by relying on a caller to not ask for more.
"""

import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.text_safety import (
    MAX_LONG_TEXT,
    MAX_MEDIUM_TEXT,
    MAX_SHORT_TEXT,
    validate_optional_phone,
    validate_optional_plain_text,
    validate_plain_text,
)
from app.models.enums import (
    AppointmentRequestStatus,
    ConversationMessageRole,
    ConversationStatus,
    HandoffStatus,
    PreferredContactMethod,
)


class PublicServiceOption(BaseModel):
    """One field beyond id/name/description on purpose: nothing else about
    a Service (price, duration, category, tenant/location linkage) is safe
    or necessary to expose publicly. Only active services are ever listed
    here — see app/services/appointment_request_service.py for the
    corresponding server-side re-validation at submission time."""

    id: uuid.UUID
    name: str
    description: str | None


class PublicLocationOption(BaseModel):
    """`timezone` is included deliberately — the widget uses the selected
    location's timezone (when one is selected) to validate the requested
    appointment date, rather than trusting the visitor's browser clock or
    an unvalidated free-text timezone."""

    id: uuid.UUID
    name: str
    timezone: str


class WidgetConfigRead(BaseModel):
    """Response for GET /api/v1/widget/{public_id}/config. Every field here
    is deliberately public-safe — see this module's docstring."""

    status: str
    business_name: str
    receptionist_name: str
    welcome_message: str
    suggested_questions: list[str]
    logo_url: str | None
    accent_color: str | None
    supported_languages: list[str]
    services: list[PublicServiceOption]
    locations: list[PublicLocationOption]
    voice_enabled: bool
    theme: dict
    launcher_position: str
    ai_disclosure: str
    privacy_notice: str
    mock_mode: bool
    business_public_email: str | None
    business_public_phone: str | None


class ContactFields(BaseModel):
    """Shared, optional inline contact capture block — embedded in the
    appointment-request and handoff-request bodies so a visitor doesn't
    need a separate round trip if they haven't already used the standalone
    contact form. `marketing_consent` here follows the exact same
    never-inferred rule as the standalone contact endpoint."""

    name: str | None = Field(default=None, max_length=MAX_SHORT_TEXT)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=32)
    preferred_contact_method: PreferredContactMethod | None = None
    marketing_consent: bool = False

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=MAX_SHORT_TEXT)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        return validate_optional_phone(v)


class WidgetContactCreate(ContactFields):
    pass


class WidgetContactCreateResponse(BaseModel):
    status: str = "received"
    contact_id: uuid.UUID
    marketing_consent: bool


class WidgetAppointmentRequestCreate(BaseModel):
    requested_date: date
    requested_time: time | None = None
    requested_time_window: str | None = Field(default=None, max_length=50)
    timezone: str = Field(max_length=64)
    notes: str | None = Field(default=None, max_length=MAX_LONG_TEXT)
    idempotency_key: str | None = Field(default=None, max_length=128)
    contact: ContactFields | None = None
    # Optional — a visitor may pick "Not sure" (omit both). Re-validated
    # server-side against the resolved tenant regardless of what's sent
    # here; see app/services/appointment_request_service.py.
    service_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None

    @field_validator("notes")
    @classmethod
    def _notes(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=MAX_LONG_TEXT)


class WidgetAppointmentRequestResponse(BaseModel):
    reference: str
    status: AppointmentRequestStatus
    requested_date: date
    requested_time: time | None
    requested_time_window: str | None
    timezone: str
    message: str = (
        "This is an appointment request, pending confirmation. "
        "The business will confirm availability and follow up with you directly."
    )


class WidgetHandoffRequestCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=MAX_MEDIUM_TEXT)
    urgency: str | None = Field(default=None, max_length=20)
    idempotency_key: str | None = Field(default=None, max_length=128)
    contact: ContactFields | None = None

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        return validate_plain_text(v, max_length=MAX_MEDIUM_TEXT)


class WidgetHandoffRequestResponse(BaseModel):
    reference: str
    status: HandoffStatus
    message: str = (
        "A team member will follow up with you as soon as possible during business hours. "
        "This request does not connect you immediately."
    )


class WidgetConversationRead(BaseModel):
    """Deliberately excludes tenant_id/receptionist_id/collected_data/
    safety_state/provider — see this module's docstring."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ConversationStatus
    locale: str
    qualification_complete: bool
    started_at: datetime
    last_message_at: datetime | None


class WidgetMessageRead(BaseModel):
    """Only ever built from USER/ASSISTANT rows — tool-call audit rows are
    never serialized through this schema (see app/api/v1/widget_public.py)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: ConversationMessageRole
    content: str
    sequence_number: int
    citations: list
    created_at: datetime


class WidgetConversationDetailResponse(BaseModel):
    conversation: WidgetConversationRead
    messages: list[WidgetMessageRead]


class WidgetSessionStartResponse(BaseModel):
    capability_token: str
    expires_at: datetime
    conversation: WidgetConversationRead
