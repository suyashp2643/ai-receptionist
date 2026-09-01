import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.text_safety import validate_optional_plain_text, validate_plain_text

MAX_FAQ_QUESTION = 500
MAX_FAQ_ANSWER = 5000


class FAQCreate(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_FAQ_QUESTION)
    answer: str = Field(min_length=1, max_length=MAX_FAQ_ANSWER)
    category: str | None = Field(default=None, max_length=120)
    source_label: str | None = Field(default=None, max_length=200)
    is_active: bool = True
    display_order: int = 0

    @field_validator("question")
    @classmethod
    def _question(cls, v: str) -> str:
        return validate_plain_text(v, max_length=MAX_FAQ_QUESTION)

    @field_validator("answer")
    @classmethod
    def _answer(cls, v: str) -> str:
        return validate_plain_text(v, max_length=MAX_FAQ_ANSWER)

    @field_validator("category", "source_label")
    @classmethod
    def _optional_short(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=200)


class FAQUpdate(BaseModel):
    question: str | None = Field(default=None, max_length=MAX_FAQ_QUESTION)
    answer: str | None = Field(default=None, max_length=MAX_FAQ_ANSWER)
    category: str | None = Field(default=None, max_length=120)
    source_label: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None
    display_order: int | None = None

    @field_validator("question")
    @classmethod
    def _question(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=MAX_FAQ_QUESTION)

    @field_validator("answer")
    @classmethod
    def _answer(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=MAX_FAQ_ANSWER)


class FAQRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    question: str
    answer: str
    category: str | None
    source_label: str | None
    is_active: bool
    display_order: int
    created_at: datetime
    updated_at: datetime


class FAQCreateResult(BaseModel):
    faq: FAQRead
    possible_duplicate_of: uuid.UUID | None = None
