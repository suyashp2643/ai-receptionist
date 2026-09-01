import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.text_safety import (
    MAX_SHORT_TEXT,
    validate_optional_phone,
    validate_optional_plain_text,
    validate_plain_text,
)
from app.core.timezones import VALID_TIMEZONES
from app.schemas.qualification import WorkingHours


class BusinessLocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_SHORT_TEXT)
    address_line: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=20)
    timezone: str = "UTC"
    public_phone: str | None = None
    working_hours: WorkingHours = Field(default_factory=WorkingHours)
    is_primary: bool = False
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return validate_plain_text(v, max_length=MAX_SHORT_TEXT)

    @field_validator("address_line", "city", "region", "country")
    @classmethod
    def _optional_short(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=300)

    @field_validator("postal_code")
    @classmethod
    def _postal_code(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=20)

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, v: str) -> str:
        if v not in VALID_TIMEZONES:
            raise ValueError(f"Unknown IANA timezone: {v!r}")
        return v

    @field_validator("public_phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        return validate_optional_phone(v)


class BusinessLocationUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=MAX_SHORT_TEXT)
    address_line: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=20)
    timezone: str | None = None
    public_phone: str | None = None
    working_hours: WorkingHours | None = None
    is_primary: bool | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return validate_optional_plain_text(v, max_length=MAX_SHORT_TEXT)

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_TIMEZONES:
            raise ValueError(f"Unknown IANA timezone: {v!r}")
        return v

    @field_validator("public_phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        return validate_optional_phone(v)


class BusinessLocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    address_line: str | None
    city: str | None
    region: str | None
    country: str | None
    postal_code: str | None
    timezone: str
    public_phone: str | None
    working_hours: dict
    is_primary: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
