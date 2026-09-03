import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AnalyticsPreset = Literal["today", "7d", "30d", "custom"]


class AnalyticsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: AnalyticsPreset = "30d"
    custom_start: date | None = None
    custom_end: date | None = None
    receptionist_id: uuid.UUID | None = None
    include_test_preview: bool = False


class AnalyticsOverviewResponse(BaseModel):
    period_start: str
    period_end: str
    receptionist_id: str | None
    include_test_preview: bool

    total_conversations: int
    genuine_widget_conversations: int
    preview_conversations: int
    test_conversations: int
    unique_visitor_sessions: int

    contacts_captured: int
    contact_capture_rate: float | None

    enquiries_created: int
    qualified_enquiries: int
    qualification_completion_rate: float | None

    appointment_requests: int
    pending_appointments: int
    confirmed_appointments: int

    human_handoffs: int
    open_handoffs: int
    resolved_handoffs: int

    unanswered_or_fallback_responses: int
    safety_interventions: int

    average_first_response_time_seconds: float | None
    average_conversation_length_messages: float | None
    conversation_completion_rate: float | None

    estimated_staff_time_saved_minutes: float
    estimated_staff_time_saved_minutes_is_estimate: bool = Field(
        default=True,
        description="Always true — this figure is a rough, configurable assumption, never a measured fact.",
    )


class TimeseriesPoint(BaseModel):
    date: str
    conversations: int
    appointment_requests: int
    human_handoffs: int


class TimeseriesResponse(BaseModel):
    points: list[TimeseriesPoint]
