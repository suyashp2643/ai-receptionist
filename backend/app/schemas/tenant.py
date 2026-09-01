import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.timezones import VALID_TIMEZONES
from app.models.enums import TenantMemberRole, TenantMemberStatus, TenantStatus


def _validate_timezone(value: str) -> str:
    if value not in VALID_TIMEZONES:
        raise ValueError(f"Unknown IANA timezone: {value!r}")
    return value


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    timezone: str = Field(default="UTC")

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        return _validate_timezone(v)


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str | None) -> str | None:
        return _validate_timezone(v) if v is not None else v


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    timezone: str
    status: TenantStatus
    created_at: datetime
    # The requesting user's role in THIS tenant — resolved server-side,
    # never accepted from the client.
    my_role: TenantMemberRole


class TenantMembershipSummary(BaseModel):
    """Used in GET /tenants and GET /auth/me — one row per tenant the caller belongs to."""

    tenant_id: uuid.UUID
    tenant_name: str
    tenant_slug: str
    role: TenantMemberRole
    status: TenantMemberStatus


class TenantMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    display_name: str
    normalized_email: str
    role: TenantMemberRole
    status: TenantMemberStatus
    created_at: datetime
