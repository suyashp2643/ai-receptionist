import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import get_settings
from app.models.enums import ConversationChannel, ConversationMessageRole, ConversationMode, ConversationStatus


class StartConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visitor_reference: str | None = Field(default=None, max_length=200)
    locale: str = Field(default="en", max_length=8)


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    receptionist_id: uuid.UUID
    mode: ConversationMode
    channel: ConversationChannel
    provider: str
    status: ConversationStatus
    visitor_reference: str | None
    locale: str
    collected_data: dict
    missing_required_fields: list
    qualification_complete: bool
    safety_state: dict
    last_error_code: str | None
    started_at: datetime
    last_message_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationRead]
    total: int
    limit: int
    offset: int


class ConversationMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: ConversationMessageRole
    content: str
    sequence_number: int
    provider_message_id: str | None
    tool_name: str | None
    tool_call_id: str | None
    tool_input: dict | None
    tool_output: dict | None
    citations: list
    safety_labels: list
    latency_ms: int | None
    token_usage: dict | None
    created_at: datetime


class ConversationSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    summary: str
    captured_requirements: dict
    unresolved_questions: list
    recommended_next_action: str | None
    generated_by_provider: str
    created_at: datetime
    updated_at: datetime


class ConversationDetailResponse(BaseModel):
    conversation: ConversationRead
    messages: list[ConversationMessageRead]
    message_total: int
    message_limit: int
    message_offset: int
    summary: ConversationSummaryRead | None = None


class SendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)
    idempotency_key: str | None = Field(default=None, max_length=128)

    @field_validator("content")
    @classmethod
    def _content(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Message content cannot be empty.")
        max_length = get_settings().max_conversation_message_length
        if len(stripped) > max_length:
            raise ValueError(f"Message is too long (max {max_length} characters).")
        return stripped


class CompleteConversationResponse(BaseModel):
    conversation: ConversationRead
    summary: ConversationSummaryRead
