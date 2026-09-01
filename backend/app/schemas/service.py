import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.text_safety import validate_optional_plain_text, validate_plain_text

_VALID_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class ServiceCreate(BaseModel):
    location_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    category: str | None = Field(default=None, max_length=120)
    price_note: str | None = Field(default=None, max_length=200)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    duration_minutes: int | None = Field(default=None, gt=0, le=1440)
    is_active: bool = True
    display_order: int = 0

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return validate_plain_text(v, max_length=200)

    @field_validator("description")
    @classmethod
    def _description(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=1000)

    @field_validator("category", "price_note")
    @classmethod
    def _optional_short(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=200)

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.upper()
        if not _VALID_CURRENCY_RE.match(v):
            raise ValueError("Currency must be a 3-letter ISO 4217 code, e.g. USD.")
        return v


class ServiceUpdate(BaseModel):
    location_id: uuid.UUID | None = None
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    category: str | None = Field(default=None, max_length=120)
    price_note: str | None = Field(default=None, max_length=200)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    duration_minutes: int | None = Field(default=None, gt=0, le=1440)
    is_active: bool | None = None
    display_order: int | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=200)

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.upper()
        if not _VALID_CURRENCY_RE.match(v):
            raise ValueError("Currency must be a 3-letter ISO 4217 code, e.g. USD.")
        return v


class ServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    location_id: uuid.UUID | None
    name: str
    description: str | None
    category: str | None
    price_note: str | None
    currency: str | None
    duration_minutes: int | None
    is_active: bool
    display_order: int
    created_at: datetime
    updated_at: datetime
