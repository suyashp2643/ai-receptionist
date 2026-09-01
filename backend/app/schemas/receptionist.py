import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.text_safety import (
    MAX_MEDIUM_TEXT,
    MAX_SHORT_TEXT,
    validate_optional_hex_color,
    validate_optional_plain_text,
    validate_plain_text,
)
from app.models.enums import ReceptionistStatus

MAX_SUGGESTED_QUESTIONS = 12


def _validate_suggested_questions(v: list[str]) -> list[str]:
    if len(v) > MAX_SUGGESTED_QUESTIONS:
        raise ValueError(f"Too many suggested questions (max {MAX_SUGGESTED_QUESTIONS}).")
    return [validate_plain_text(q, max_length=MAX_SHORT_TEXT) for q in v]


class ReceptionistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_SHORT_TEXT)
    welcome_message: str = Field(default="", max_length=MAX_MEDIUM_TEXT)
    tone: str | None = Field(default=None, max_length=50)
    default_language: str = "en"
    supported_languages: list[str] = Field(default_factory=lambda: ["en"])
    logo_url: str | None = Field(default=None, max_length=500)
    accent_color: str | None = None
    suggested_questions: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return validate_plain_text(v, max_length=MAX_SHORT_TEXT)

    @field_validator("welcome_message")
    @classmethod
    def _welcome_message(cls, v: str) -> str:
        if v == "":
            return v
        return validate_plain_text(v, max_length=MAX_MEDIUM_TEXT)

    @field_validator("tone")
    @classmethod
    def _tone(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=50)

    @field_validator("logo_url")
    @classmethod
    def _logo_url(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("logo_url must start with http:// or https://")
        return v

    @field_validator("accent_color")
    @classmethod
    def _accent_color(cls, v: str | None) -> str | None:
        return validate_optional_hex_color(v)

    @field_validator("suggested_questions")
    @classmethod
    def _suggested_questions(cls, v: list[str]) -> list[str]:
        return _validate_suggested_questions(v)


class ReceptionistUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=MAX_SHORT_TEXT)
    welcome_message: str | None = Field(default=None, max_length=MAX_MEDIUM_TEXT)
    tone: str | None = Field(default=None, max_length=50)
    default_language: str | None = None
    supported_languages: list[str] | None = None
    logo_url: str | None = Field(default=None, max_length=500)
    accent_color: str | None = None
    suggested_questions: list[str] | None = None
    status: ReceptionistStatus | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=MAX_SHORT_TEXT)

    @field_validator("welcome_message")
    @classmethod
    def _welcome_message(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=MAX_MEDIUM_TEXT)

    @field_validator("tone")
    @classmethod
    def _tone(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=50)

    @field_validator("accent_color")
    @classmethod
    def _accent_color(cls, v: str | None) -> str | None:
        return validate_optional_hex_color(v)

    @field_validator("suggested_questions")
    @classmethod
    def _suggested_questions(cls, v: list[str] | None) -> list[str] | None:
        return _validate_suggested_questions(v) if v is not None else None


class ReceptionistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    industry_template_id: uuid.UUID | None
    template_version: int | None
    name: str
    welcome_message: str
    tone: str | None
    default_language: str
    supported_languages: list
    logo_url: str | None
    accent_color: str | None
    suggested_questions: list
    status: ReceptionistStatus
    created_at: datetime
    updated_at: datetime
