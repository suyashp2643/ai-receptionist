import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.text_safety import MAX_LONG_TEXT, MAX_MEDIUM_TEXT, validate_optional_plain_text, validate_plain_text
from app.models.enums import WidgetInstallationStatus

_ALLOWED_LAUNCHER_POSITIONS = frozenset({"bottom-right", "bottom-left"})
MAX_ALLOWED_DOMAINS = 20


class WidgetInstallationCreate(BaseModel):
    receptionist_id: uuid.UUID
    allowed_domains: list[str] = Field(default_factory=list)
    launcher_position: str = "bottom-right"
    privacy_notice: str = ""
    ai_disclosure: str | None = None

    @field_validator("launcher_position")
    @classmethod
    def _launcher_position(cls, v: str) -> str:
        if v not in _ALLOWED_LAUNCHER_POSITIONS:
            raise ValueError(f"launcher_position must be one of {sorted(_ALLOWED_LAUNCHER_POSITIONS)}.")
        return v

    @field_validator("privacy_notice")
    @classmethod
    def _privacy_notice(cls, v: str) -> str:
        if not v:
            return ""
        return validate_plain_text(v, max_length=MAX_LONG_TEXT)

    @field_validator("ai_disclosure")
    @classmethod
    def _ai_disclosure(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=MAX_MEDIUM_TEXT)


class WidgetInstallationUpdate(BaseModel):
    allowed_domains: list[str] | None = None
    theme: dict | None = None
    launcher_position: str | None = None
    privacy_notice: str | None = None
    ai_disclosure: str | None = None

    @field_validator("launcher_position")
    @classmethod
    def _launcher_position(cls, v: str | None) -> str | None:
        if v is not None and v not in _ALLOWED_LAUNCHER_POSITIONS:
            raise ValueError(f"launcher_position must be one of {sorted(_ALLOWED_LAUNCHER_POSITIONS)}.")
        return v

    @field_validator("privacy_notice")
    @classmethod
    def _privacy_notice(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=MAX_LONG_TEXT)

    @field_validator("ai_disclosure")
    @classmethod
    def _ai_disclosure(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=MAX_MEDIUM_TEXT)


class WidgetInstallationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    receptionist_id: uuid.UUID
    public_id: str
    status: WidgetInstallationStatus
    allowed_domains: list[str]
    theme: dict
    launcher_position: str
    privacy_notice: str
    ai_disclosure: str
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None
